#!/usr/bin/env python
"""
resweep_universe.py -- scheduled frame-free re-sweep of ENA for the Infant Gut
Shotgun-Metagenome Catalog.

Pulls every ENA read_run made public since --since in three slices, aggregates to
study level, applies the deterministic human-signal rule of the 2026-09-24
frame-free sweep (frame_free_sweep_report.md, reproduced verbatim below) and the
deterministic auto-exclude, diffs against catalog_studies.parquet and writes a
candidate table that run_sonnet_confirm.py can consume directly.

Slices (all with first_public>=SINCE):
  S1 shotgun_frame_free      library_source="METAGENOMIC" AND strategy in (WGS, WXS), NO taxon
  S2 misfiled_genomic_primary library_source="GENOMIC" AND strategy in (WGS, WXS) AND
                              tax_eq(<scope_constants.TAXA_PRIMARY>)
  S3 adjudication_host9606   library_source="METAGENOMIC" AND strategy in (OTHER, Targeted-Capture)
                              AND host_tax_id=9606
  S3b adjudication_tax9606   same strategies AND tax_eq(9606)   (skill rule 2026-09-18)

Paging: ENA `offset` is unreliable -> every slice is one limit=0 stream parsed in
100k-row chunks into a pyarrow ParquetWriter; every slice row count is compared with
the ENA count endpoint and any mismatch is reported.

No LLM calls. All HTTP through harvest_lib (cached in ./harvest_cache/).

Usage:
  python resweep_universe.py --since 2026-09-01 --catalog catalog_studies.parquet --out resweep_out
  python resweep_universe.py --since 2026-09-01 --catalog catalog_studies.parquet --dry-run
"""
# --- microbiome_repo-pipeline repo layout shim (added 2026-09-26; original ran flat from one cwd) ---
import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__)) if "__file__" in globals() else _os.getcwd()
for _p in (_here, _os.path.join(_here, "..", "..")):
    _p = _os.path.abspath(_p)
    if _p not in _sys.path:
        _sys.path.insert(0, _p)
try:
    from catalog.models import resolve_model, set_host  # registers src/catalog/<stage>/ dirs on sys.path
except ImportError:  # flat-workspace mode (files copied side by side): models.py must sit alongside
    from models import resolve_model, set_host
set_host(globals().get("host"))  # kernel `host` is a frame global, not builtins (R1-01)
def _prompt_path(name):
    """cwd copy first (leaf-worker convention), else the packaged prompt under src/catalog/prompts/."""
    for _c in (name, _os.path.join("pilot_prompts", name), _os.path.join(_here, "..", "prompts", name)):
        if _os.path.exists(_c):
            return _c
    return name
# ---------------------------------------------------------------------------------------------
import argparse
import io
import warnings
import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# (sys.path handled by the repo layout shim above)
import harvest_lib as HL            # noqa: E402
import scope_constants as SC        # noqa: E402
import aggregate_studies as AGG     # noqa: E402

warnings.filterwarnings("ignore", message="This pattern is interpreted as a regular expression")
CHUNK = 100_000
STUDY_BATCH = 40
RUN_BATCH = 20

# 43 lean ENA fields + found_by == the 44-column universe_runs contract
LEAN_FIELDS = [
    "run_accession", "study_accession", "secondary_study_accession",
    "sample_accession", "secondary_sample_accession", "experiment_accession",
    "library_strategy", "library_source", "library_selection", "library_layout",
    "library_name", "target_gene", "instrument_platform", "instrument_model",
    "read_count", "base_count", "nominal_length",
    "tax_id", "scientific_name", "host_tax_id", "host_scientific_name",
    "host_body_site", "host_status", "host_phenotype", "age", "dev_stage",
    "disease", "country", "first_public", "center_name", "project_name",
    "study_title", "sample_title", "serovar", "sub_species", "strain",
    "isolate", "checklist", "environmental_medium", "isolation_source",
    "experimental_factor", "extraction_protocol", "environmental_sample",
]
assert len(LEAN_FIELDS) == 43
# two extra sample fields the human-signal rule reads (kept out of the 44-col runs table)
SIGNAL_EXTRA = ["host", "environment_material"]
PULL_FIELDS = LEAN_FIELDS + SIGNAL_EXTRA
RUN_SCHEMA = pa.schema([(c, pa.string()) for c in PULL_FIELDS] + [("slice_tag", pa.string())])
RUNS_OUT_COLS = LEAN_FIELDS + ["found_by"]

# --------------------------------------------------------------------------- rule
# Verbatim regexes of the 2026-09-24 frame-free sweep (frame 82daaf0b, final version).
SITE_RE = re.compile(r"\bgut\b|\bstool|\bfaec|\bfecal|\bfeces|\bintestin|\bmeconium", re.I)
HSPEC_RE = re.compile(r"\bhuman|\bhomo sapiens|\binfant|\bneonat|\bnewborn|\bpreterm|\bchild|"
                      r"\bpatient|\bvolunteer|breast milk|\bdonor|\bcohort", re.I)
ANIMAL_ENV_RE = re.compile(
    r"\b(mouse|mice|murine|rats?|pigs?|piglets?|swine|porcine|chickens?|poultry|broilers?|cattle|"
    r"bovine|cows?|calf|calves|dogs?|canine|cats?|feline|fish|zebrafish|soil|sediments?|wastewater|"
    r"sewage|marine|reactor|bioreactor|compost|plants?|rumen|insects?|termites?|sheep|ovine|goats?|"
    r"invertebrates?|bees?|honeybee|birds?|avian|bats?|primates?|macaques?|shrimps?|manure|horses?|"
    r"equine|rabbits?|drosophila|mosquito|aquaculture|seawater|freshwater|lake|river|sludge|ocean|"
    r"glacier|permafrost|hot spring|biofilm|fermentation|fermented|cheese|kimchi|sourdough|wine|kefir|"
    r"silage|phyllosphere|rhizosphere|aquifer|groundwater|estuary|hydrothermal|dust|indoor|leopards?|"
    r"tigers?|lions?|pandas?|monkeys?|deer|elephants?|whales?|dolphins?|seals?|penguins?|frogs?|"
    r"turtles?|lizards?|snakes?|corals?|sponges?|oysters?|mussels?|snails?|squid|fly|flies|larvae?|"
    r"beetles?|moths?|worms?|nematodes?|wild|captive|zoo|livestock|animals?|veterinary|yaks?|camels?|"
    r"buffalo|donkeys?|ruminants?|ducks?|geese|goose|turkeys?|quail|salmon|trout|tilapia|carp|crabs?|"
    r"lobsters?|earthworms?|silkworms?|aphids?|wasps?|ants?|cockroach|ticks?|spiders?|koala|kangaroo|"
    r"hamsters?|guinea pig|ferrets?|mink|fox|wolf|bears?|boars?|gorillas?|chimpanzees?|orangutans?|"
    r"lemurs?|marmosets?|baboons?|mus musculus|gallus gallus|sus scrofa|rattus|bos taurus|canis lupus|"
    r"felis catus|danio rerio|apis mellifera|ovis aries|capra hircus|macaca)\b", re.I)
SAMPLE_TEXT_COLS = ["host", "host_body_site", "isolation_source", "environmental_medium",
                    "environment_material", "sample_title", "dev_stage"]
NON_SPECIES_TOKENS = ["metagenome", "uncultured", "unidentified", "bacterium", "virus", "synthetic",
                      "mixed culture", "homo sapiens", "unclassified", "environmental", "phage", "archaeon"]


def _terms(rx, s):
    return sorted(set(m.group(0).lower() for m in rx.finditer(s or "")))


def species_taxon(sn):
    """True when the sample taxon is a non-metagenome Latin binomial (e.g. Zeugodacus cucurbitae)."""
    for x in [x for x in (sn or "").split(";") if x]:
        xl = x.lower()
        if any(k in xl for k in NON_SPECIES_TOKENS):
            continue
        if re.match(r"^[A-Z][a-z]+ [a-z]+", x):
            return True
    return False


def human_signal(runs, studies_meta):
    """
    Deterministic human-signal rule (frame_free_sweep_report.md, 'Human-signal rule').
    runs: run-level frame with PULL_FIELDS; studies_meta: study_accession, study_title,
    description (from ENA result=study, may be empty).
    Returns a study-level frame with scores, rule tag, ambiguous flag, human_signal_reason.
    """
    ns = runs.copy()
    for c in SAMPLE_TEXT_COLS + ["host_scientific_name", "host_tax_id", "scientific_name", "tax_id"]:
        if c not in ns:
            ns[c] = ""
        ns[c] = ns[c].fillna("").astype(str)
    ns["sample_text"] = ns[SAMPLE_TEXT_COLS].agg(" | ".join, axis=1)
    ns["run_human_host"] = ((ns.host_tax_id == "9606")
                            | ns.host_scientific_name.str.contains(r"homo sapiens|\bhuman", case=False, regex=True)
                            | ns.host.str.contains(r"homo sapiens|\bhuman\b", case=False, regex=True))
    ns["run_nonhuman_host"] = (ns.host_tax_id != "") & (ns.host_tax_id != "9606")
    ns["run_hspec"] = ns.sample_text.str.contains(HSPEC_RE)
    ns["run_site"] = ns.sample_text.str.contains(SITE_RE)
    ns["run_animal"] = (ns.sample_text + " || " + ns.host_scientific_name).str.contains(ANIMAL_ENV_RE)
    ns["run_animal_terms"] = ""
    ns.loc[ns.run_animal, "run_animal_terms"] = (ns.sample_text + " || " + ns.host_scientific_name)[ns.run_animal].map(
        lambda s: ";".join(_terms(ANIMAL_ENV_RE, s)[:3]))
    g = ns.groupby("study_accession")
    agg = g.agg(n_runs=("run_accession", "size"),
                n_runs_human_host=("run_human_host", "sum"),
                n_runs_nonhuman_host=("run_nonhuman_host", "sum"),
                n_runs_hspec=("run_hspec", "sum"),
                n_runs_site=("run_site", "sum"),
                n_runs_animal=("run_animal", "sum"),
                run_animal_terms=("run_animal_terms", lambda s: ";".join(sorted(set(t for x in s for t in x.split(";") if t))[:4])),
                tax_ids_rule=("tax_id", lambda s: ";".join(sorted(set(s)))),
                scientific_names_rule=("scientific_name", lambda s: ";".join(sorted(set(s)))),
                run_study_title=("study_title", "first")).reset_index()
    agg = agg.merge(studies_meta[["study_accession", "study_title", "description"]], how="left",
                    on="study_accession")
    agg["study_title"] = agg.study_title.fillna("").where(agg.study_title.fillna("") != "", agg.run_study_title)
    agg["description"] = agg.description.fillna("")
    agg["study_text"] = agg.study_title.fillna("") + " | " + agg.description
    agg["site_terms"] = agg.study_text.map(lambda s: _terms(SITE_RE, s))
    agg["hspec_terms"] = agg.study_text.map(lambda s: _terms(HSPEC_RE, s))
    agg["animal_terms"] = (agg.study_text + " || " + agg.scientific_names_rule).map(lambda s: _terms(ANIMAL_ENV_RE, s))
    agg["taxon_name_human"] = agg.scientific_names_rule.str.contains(r"\bhuman", case=False, regex=True)
    agg["taxon_nonhuman_species"] = agg.scientific_names_rule.map(species_taxon)
    agg["human_specific_score"] = (agg.hspec_terms.map(len) + (agg.n_runs_hspec > 0).astype(int)
                                   + agg.taxon_name_human.astype(int))
    agg["site_score"] = agg.site_terms.map(len) + (agg.n_runs_site > 0).astype(int)
    agg["animal_score"] = (agg.animal_terms.map(len) + (agg.n_runs_animal > 0).astype(int)
                           + agg.taxon_nonhuman_species.astype(int)
                           + ((agg.n_runs_nonhuman_host > 0) & (agg.n_runs_human_host == 0)).astype(int))
    ruleA = agg.n_runs_human_host > 0
    ruleB = (agg.animal_score == 0) & ((agg.human_specific_score > 0) | (agg.site_score > 0))
    ruleC = (agg.animal_score > 0) & (agg.human_specific_score > agg.animal_score)
    agg["human_signal"] = ruleA | ruleB | ruleC
    agg["signal_rule"] = np.select([ruleA, ruleB, ruleC],
                                   ["A_host_human", "B_no_animal_terms", "C_human_specific_outweighs_animal"],
                                   default="")
    # ties (animal_score >= human_specific_score with both > 0) are excluded by design and flagged
    agg["ambiguous"] = ~agg.human_signal & (agg.human_specific_score > 0) & (agg.animal_score > 0)

    def reason(r):
        p = []
        if r.n_runs_human_host > 0:
            p.append(f"host_tax_id=9606/host~human on {r.n_runs_human_host}/{r.n_runs} runs")
        if r.taxon_name_human:
            p.append(f"taxon name: {r.scientific_names_rule}")
        if r.hspec_terms:
            p.append("human-specific terms in title/description: " + ";".join(r.hspec_terms[:5]))
        if r.n_runs_hspec:
            p.append(f"human-specific terms in sample fields on {r.n_runs_hspec}/{r.n_runs} runs")
        if r.site_terms:
            p.append("gut/stool terms: " + ";".join(r.site_terms[:4]))
        if r.n_runs_site and not r.site_terms:
            p.append(f"gut/stool terms in sample fields on {r.n_runs_site}/{r.n_runs} runs")
        if r.animal_score > 0:
            p.append(f"animal/env signal (score {r.animal_score}, {'outweighed' if r.human_signal else 'dominant'}): "
                     + ";".join(r.animal_terms[:5])
                     + (";nonhuman_host_tax_id" if (r.n_runs_nonhuman_host > 0 and r.n_runs_human_host == 0) else "")
                     + (";species taxon" if r.taxon_nonhuman_species else "")
                     + (f";sample fields on {r.n_runs_animal}/{r.n_runs} runs: {r.run_animal_terms}" if r.n_runs_animal else ""))
        return f"[{r.signal_rule or 'no_signal'}] " + ("; ".join(p) if p else "no human signal")

    agg["human_signal_reason"] = agg.apply(reason, axis=1)
    for c in ["site_terms", "hspec_terms", "animal_terms"]:
        agg[c] = agg[c].map(";".join)
    return agg.drop(columns=["study_text", "run_study_title"])


def auto_exclude(st):
    """
    Deterministic auto-exclude on the aggregated study rows:
      * sig_synthetic non-empty                              -> host_synthetic
      * sig_nonhuman_host non-empty, no infant term, no human host run -> host_nonhuman
      * animal/environment term in the study TITLE, no infant term, no human host run
                                                             -> host_nonhuman / host_environmental
    'Infant protection': a study whose text carries an infant term (sig_infant_hit) or that has
    a human-host run (rule A) is never auto-excluded on host text -- it goes to the rubric.
    Returns (flag Series, reason Series).
    """
    synthetic = st.sig_synthetic.fillna("[]") != "[]"
    nonhuman = st.sig_nonhuman_host.fillna("[]") != "[]"
    title_animal = st.study_title.fillna("").map(lambda t: bool(ANIMAL_ENV_RE.search(t)))
    protected = st.sig_infant_hit.astype(bool) | (st.signal_rule == "A_host_human")
    flag = synthetic | (nonhuman & ~protected) | (title_animal & ~protected)
    reason = np.select(
        [synthetic, nonhuman & ~protected, title_animal & ~protected],
        ["host_synthetic: " + st.sig_synthetic.fillna(""),
         "host_nonhuman: " + st.sig_nonhuman_host.fillna(""),
         "host_nonhuman/environmental title term: "
         + st.study_title.fillna("").map(lambda t: ";".join(_terms(ANIMAL_ENV_RE, t)[:4]))],
        default="")
    return pd.Series(flag, index=st.index), pd.Series(reason, index=st.index)


# --------------------------------------------------------------------------- pull
def build_slices(since):
    d = f"first_public>={since}"
    prim = SC.ena_taxon_clause(SC.TAXA_PRIMARY)
    return [
        ("shotgun_frame_free", f"{SC.ena_shotgun_clause()} AND {d}"),
        ("misfiled_genomic_primary", f"{SC.ena_misfiled_genomic_clause()} AND {prim} AND {d}"),
        ("adjudication_host9606", f"{SC.ena_adjudicate_clause()} AND host_tax_id=9606 AND {d}"),
        ("adjudication_tax9606", f"{SC.ena_adjudicate_clause()} AND tax_eq(9606) AND {d}"),
    ]


def stream_pull(query, tag, out_dir, log):
    expected = HL.ena_count("read_run", query, purpose=f"resweep_count:{tag}")
    out_f = out_dir / f"runs_{tag}.parquet"
    if not expected:
        log(f"  [{tag}] expected {expected} -- skipped")
        return expected or 0, 0, None
    t0 = time.time()
    tsv = HL.ena_search("read_run", query, PULL_FIELDS, limit=0, purpose=f"resweep:{tag}")
    if not tsv or not tsv.strip():
        log(f"  [{tag}] EMPTY body (expected {expected})")
        return expected, 0, None
    got, writer = 0, None
    for chunk in pd.read_csv(io.StringIO(tsv), sep="\t", dtype=str, on_bad_lines="skip",
                             low_memory=False, chunksize=CHUNK, keep_default_na=False):
        for c in PULL_FIELDS:
            if c not in chunk:
                chunk[c] = ""
        chunk = chunk[PULL_FIELDS].copy()
        chunk["slice_tag"] = tag
        tbl = pa.Table.from_pandas(chunk, schema=RUN_SCHEMA, preserve_index=False)
        if writer is None:
            writer = pq.ParquetWriter(out_f, RUN_SCHEMA, compression="zstd")
        writer.write_table(tbl)
        got += len(chunk)
    if writer:
        writer.close()
    del tsv
    status = "OK" if expected == got else f"MISMATCH (expected {expected})"
    log(f"  [{tag}] rows={got:,} {status} {time.time()-t0:.0f}s")
    return expected, got, out_f


def fetch_study_meta(accs, log):
    """ENA result=study rows (title, description, center_name) in batches of STUDY_BATCH."""
    rows = []
    accs = sorted(set(a for a in accs if a))
    fields = ["study_accession", "study_title", "description", "center_name", "first_public"]
    for i in range(0, len(accs), STUDY_BATCH):
        b = accs[i:i + STUDY_BATCH]
        q = " OR ".join(f'study_accession="{a}"' for a in b)
        tsv = HL.ena_search("study", q, fields, limit=0, purpose="resweep_study_meta")
        if tsv and tsv.strip():
            df = pd.read_csv(io.StringIO(tsv), sep="\t", dtype=str, keep_default_na=False)
            rows.append(df)
    meta = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=fields)
    for c in fields:
        if c not in meta:
            meta[c] = ""
    missing = len(accs) - meta.study_accession.nunique()
    log(f"  study metadata: {meta.study_accession.nunique():,}/{len(accs):,} studies have an ENA study record "
        f"({missing} SRA/DDBJ-mirrored without one -> title from read_run, description empty)")
    return meta.drop_duplicates("study_accession"), missing


def fetch_study_runs(accs, log):
    """Every read_run row of the given studies (no strategy/source/date constraint), RUN_BATCH per call."""
    rows = []
    accs = sorted(set(a for a in accs if a))
    for i in range(0, len(accs), RUN_BATCH):
        b = accs[i:i + RUN_BATCH]
        q = "(" + " OR ".join(f'study_accession="{s}"' for s in b) + ")"
        tsv = HL.ena_search("read_run", q, PULL_FIELDS, limit=0, purpose="resweep_study_runs")
        if tsv and tsv.strip():
            df = pd.read_csv(io.StringIO(tsv), sep="\t", dtype=str, keep_default_na=False, on_bad_lines="skip")
            for c in PULL_FIELDS:
                if c not in df:
                    df[c] = ""
            rows.append(df[PULL_FIELDS])
    full = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=PULL_FIELDS)
    log(f"  full-study pull: {len(full):,} runs across {full.study_accession.nunique():,} studies "
        f"({len(accs)} requested, {len(accs) // RUN_BATCH + 1} calls)")
    return full.drop_duplicates("run_accession")


# --------------------------------------------------------------------------- main
CONTRACT_COLS = ["study_accession", "study_title", "n_runs", "n_samples", "first_public_min",
                 "library_strategies", "library_sources", "instrument_models", "host_scientific_names",
                 "host_tax_ids", "scientific_names", "host_body_sites", "ages", "dev_stages",
                 "isolation_sources", "environmental_medium", "sample_titles_sample", "countries",
                 "center_name", "sig_infant_hit", "sig_nonhuman_host", "sig_synthetic",
                 "discovery_channel", "discovery_evidence"]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", required=True, help="YYYY-MM-DD; first_public>=SINCE")
    ap.add_argument("--out", default="resweep_out", help="output directory")
    ap.add_argument("--catalog", default="catalog_studies.parquet",
                    help="catalog_studies.parquet (study_accession column) to diff against")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the slice queries and ENA counts, pull nothing")
    ap.add_argument("--no-complete", action="store_true",
                    help="do NOT re-pull the full run list of the not-in-catalog studies (judge on the "
                         "date-window runs only; faster, less faithful)")
    a = ap.parse_args(argv)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", a.since):
        ap.error("--since must be YYYY-MM-DD")
    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = []

    def log(s):
        print(s, flush=True)
        lines.append(s)

    t_start = time.time()
    slices = build_slices(a.since)
    log(f"# resweep since {a.since}  ({time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())})")
    if a.dry_run:
        for tag, q in slices:
            n = HL.ena_count("read_run", q, purpose=f"resweep_dryrun:{tag}")
            log(f"  [{tag}] count={n}  query={q}")
        return 0

    catalog = pd.read_parquet(a.catalog, columns=["study_accession"])
    catalog_set = set(catalog.study_accession.dropna())
    log(f"catalog: {len(catalog_set):,} studies ({a.catalog})")

    # 1. pull
    audit, files = [], []
    for tag, q in slices:
        exp, got, f = stream_pull(q, tag, out_dir, log)
        audit.append({"slice": tag, "query": q, "ena_count": exp, "rows_pulled": got,
                      "complete": exp == got})
        if f:
            files.append(f)
    pd.DataFrame(audit).to_csv(out_dir / f"resweep_{a.since}_audit.csv", index=False)
    if not files:
        log("no runs pulled in any slice; nothing to do")
        return 0
    runs = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    n_raw = len(runs)
    n_blank_study = int((runs.study_accession == "").sum())
    runs = runs[runs.study_accession != ""]
    found_by = runs.groupby("run_accession").slice_tag.agg(lambda s: ";".join(sorted(set(s))))
    runs = runs.drop_duplicates("run_accession").copy()
    runs["found_by"] = runs.run_accession.map(found_by)
    runs.drop(columns=["slice_tag"]).to_parquet(out_dir / f"resweep_{a.since}_runs_all.parquet", index=False)
    log(f"pulled {n_raw:,} rows -> {len(runs):,} unique runs / {runs.study_accession.nunique():,} studies "
        f"({n_blank_study} rows with empty study_accession dropped)")

    # 2. diff against catalog
    runs["in_catalog"] = runs.study_accession.isin(catalog_set)
    n_studies_in_cat = runs[runs.in_catalog].study_accession.nunique()
    new_runs = runs[~runs.in_catalog].copy()
    new_studies = sorted(new_runs.study_accession.unique())
    log(f"studies already in catalog: {n_studies_in_cat:,}; NOT in catalog: {len(new_studies):,} "
        f"({len(new_runs):,} runs)")
    if not new_studies:
        (out_dir / f"resweep_{a.since}_report.md").write_text("\n".join(lines) + "\n")
        return 0

    # 2b. complete the new studies: a date-window slice sees only the runs released since SINCE,
    #     but the rule must judge the WHOLE deposit (older runs may carry the host / taxon signal).
    if not a.no_complete:
        full = fetch_study_runs(new_studies, log)
        if len(full):
            full = full[~full.run_accession.isin(set(new_runs.run_accession))].copy()
            full["found_by"] = "study_completion"
            full["in_catalog"] = False
            new_runs = pd.concat([new_runs, full[new_runs.columns.intersection(full.columns)]], ignore_index=True)
            for c in new_runs.columns:
                if new_runs[c].dtype == object:
                    new_runs[c] = new_runs[c].fillna("")
            log(f"  study completion: +{len(full):,} older runs -> {len(new_runs):,} runs in the new studies")

    # 3. study metadata + aggregation (aggregate_studies.build on the 44-column table)
    meta, n_meta_missing = fetch_study_meta(new_studies, log)
    lean_path = out_dir / f"_tmp_new_runs_lean.parquet"
    new_runs[RUNS_OUT_COLS].to_parquet(lean_path, index=False)
    st = AGG.build(str(lean_path), str(out_dir / f"_tmp_new_studies_agg.parquet"))
    lean_path.unlink(missing_ok=True)
    (out_dir / f"_tmp_new_studies_agg.parquet").unlink(missing_ok=True)
    # prefer the ENA study record's title/center when read_run left them blank
    st = st.merge(meta[["study_accession", "study_title", "description", "center_name"]]
                  .rename(columns={"study_title": "study_title_ena", "center_name": "center_name_ena",
                                   "description": "study_description"}),
                  how="left", on="study_accession")
    st["study_title"] = st.study_title.where(st.study_title.fillna("") != "", st.study_title_ena.fillna(""))
    st["center_name"] = st.center_name.where(st.center_name.fillna("") != "", st.center_name_ena.fillna(""))
    st["study_description"] = st.study_description.fillna("")
    st = st.drop(columns=["study_title_ena", "center_name_ena"])

    # 4. human-signal rule + auto-exclude
    sig = human_signal(new_runs, meta.assign(description=meta.description))
    st = st.merge(sig.drop(columns=["study_title", "description", "n_runs"]), how="left", on="study_accession")
    st["human_signal"] = st.human_signal.fillna(False).astype(bool)
    st["ambiguous"] = st.ambiguous.fillna(False).astype(bool)
    st["signal_rule"] = st.signal_rule.fillna("")
    st["auto_exclude"], st["auto_exclude_reason"] = auto_exclude(st)
    st["discovery_channel"] = "resweep_" + a.since + ":" + st.found_by.fillna("")
    st["discovery_evidence"] = st.human_signal_reason.fillna("")
    st["resweep_since"] = a.since
    st["blank_taxon"] = st.tax_ids.fillna("") == ""
    # columns run_sonnet_confirm.py's fmt() reads beyond the contract
    for c, v in [("sig_infant_title", False), ("matched_patterns", ""), ("screen_value", ""),
                 ("prior_verdict", ""), ("record_json", "{}")]:
        if c not in st:
            st[c] = v
    st["record_json"] = st.apply(lambda r: json.dumps({"env_medium": r.environmental_medium,
                                                        "sample_titles": r.sample_titles_sample}), axis=1)

    all_path = out_dir / f"resweep_{a.since}_all_new_studies.parquet"
    st.to_parquet(all_path, index=False)
    cand = st[st.human_signal].copy()
    cand_path = out_dir / f"resweep_{a.since}_candidates.parquet"
    cand.to_parquet(cand_path, index=False)
    cand_runs = new_runs[new_runs.study_accession.isin(set(cand.study_accession))][RUNS_OUT_COLS]
    cand_runs.to_parquet(out_dir / f"resweep_{a.since}_candidate_runs.parquet", index=False)
    feed = cand[~cand.auto_exclude]
    feed.to_parquet(out_dir / f"resweep_{a.since}_for_sonnet_confirm.parquet", index=False)

    # 5. report
    def md(df, cols):
        d = df[cols].copy()
        for c in d.columns:
            if d[c].dtype == object:
                d[c] = d[c].astype(str).str.replace("|", "/").str.slice(0, 90)
        return ("| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
                + "\n".join("| " + " | ".join(str(v) for v in r) + " |" for r in d.itertuples(index=False)))

    rules = cand.signal_rule.value_counts().to_dict()
    rep = [f"# Re-sweep of ENA since {a.since}",
           f"Generated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}; runtime {time.time()-t_start:.0f}s; "
           f"catalog {a.catalog} ({len(catalog_set):,} studies).",
           "", "## Pull", md(pd.DataFrame(audit), ["slice", "ena_count", "rows_pulled", "complete"]), "",
           f"* {n_raw:,} rows -> {len(runs):,} unique runs / {runs.study_accession.nunique():,} studies; "
           f"{n_blank_study} rows with empty study_accession dropped.",
           f"* Studies already in catalog: {n_studies_in_cat:,}. **Not in catalog: {len(new_studies):,}** ({len(new_runs):,} runs).",
           f"* {n_meta_missing} new studies have no ENA study record (title from read_run, description empty).",
           "", "## Human-signal rule (deterministic; frame_free_sweep_report.md 2026-09-24)",
           f"* human-signal studies: **{len(cand)}** ({int(cand.n_runs.sum()):,} runs) -- rule A {rules.get('A_host_human',0)}, "
           f"rule B {rules.get('B_no_animal_terms',0)}, rule C {rules.get('C_human_specific_outweighs_animal',0)}",
           f"* ambiguous (human terms but animal/env score >= human score; excluded by design, kept in all_new_studies): "
           f"{int(st.ambiguous.sum())}",
           f"* no signal: {int((~st.human_signal & ~st.ambiguous).sum())}",
           f"* blank tax_id among human-signal studies: {int(cand.blank_taxon.sum())}",
           f"* sig_infant_hit among human-signal studies: {int(cand.sig_infant_hit.sum())}",
           "", "## Deterministic auto-exclude",
           f"* auto_exclude=True: {int(cand.auto_exclude.sum())} of {len(cand)} human-signal studies "
           f"(synthetic {int(cand.auto_exclude_reason.str.startswith('host_synthetic').sum())}, "
           f"nonhuman host text {int(cand.auto_exclude_reason.str.startswith('host_nonhuman:').sum())}, "
           f"animal/env title term {int(cand.auto_exclude_reason.str.startswith('host_nonhuman/env').sum())})",
           f"* **{len(feed)} studies to feed run_sonnet_confirm.py** (resweep_{a.since}_for_sonnet_confirm.parquet); "
           f"{int(feed.sig_infant_hit.sum())} carry an infant term.",
           "", "## Infant-term human-signal studies",
           md(cand[cand.sig_infant_hit].sort_values("n_runs", ascending=False),
              ["study_accession", "scientific_names", "n_runs", "first_public_min", "study_title", "auto_exclude"]) if cand.sig_infant_hit.any() else "(none)",
           "", "## Ambiguous studies (human terms present, animal/env score >= human score; excluded by design)",
           md(st[st.ambiguous].sort_values("n_runs", ascending=False),
              ["study_accession", "n_runs", "study_title", "human_signal_reason"]) if st.ambiguous.any() else "(none)",
           "", "## Files",
           f"* resweep_{a.since}_candidates.parquet -- human-signal studies not in catalog (OUTPUT CONTRACT + rule columns + auto_exclude)",
           f"* resweep_{a.since}_for_sonnet_confirm.parquet -- candidates minus auto_exclude; SLICE input for run_sonnet_confirm.py",
           f"* resweep_{a.since}_candidate_runs.parquet -- 44-column read_run rows of the candidate studies",
           f"* resweep_{a.since}_all_new_studies.parquet -- every not-in-catalog study incl. ambiguous / no-signal",
           f"* resweep_{a.since}_runs_all.parquet -- every pulled run (all slices, deduplicated, found_by)",
           f"* resweep_{a.since}_audit.csv -- per-slice ENA count vs rows pulled",
           "", "## Log", "```", *lines, "```"]
    (out_dir / f"resweep_{a.since}_report.md").write_text("\n".join(rep) + "\n")
    log(f"done in {time.time()-t_start:.0f}s -> {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

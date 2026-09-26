"""
Step 2 (v3, 2026-09-24) -- enumeration of the human DNA-shotgun metagenome universe with
the growth-phase discoveries made into standing slices. Keeps every v2 slice and adds:

  (a) human milk metagenome taxid fixed to 1633571 (1633408 retired). While verifying, two
      more v2 ids proved wrong: 1131769 is "human nasopharyngeal metagenome" (not milk;
      milk metagenome = 1616037) and 1348798 is "terrestrial metagenome" (not human vaginal;
      human vaginal metagenome = 1632839). Both fixed; old ids in TAXA_RETIRED.
  (b) TAXA_VIROME {human viral metagenome 2489051, viral metagenome 1070528}, resolved via an
      ENA read_run probe (scientific_name="<name>" -> tax_id), enumerated as a tagged
      secondary frame (slice tag 'virome').
  (c) MISFILED slice: library_source="GENOMIC" AND library_strategy in (WGS, WXS) on
      TAXA_PRIMARY + milk + vaginal taxa, tag 'misfiled_genomic' (adjudication, never
      auto-include).
  (d) OTHER/Targeted-Capture slices for tax_eq(9606) and every frame taxon, tag
      'adjudication_other' (v2 already ran these; v3 names the tag).
  (e) per-slice `slice_tag` column on every run row; aggregated per study as
      `enumeration_channels` (slice names, ';'-joined) and `enumeration_tags`.

Every taxid in the frame is re-verified against ENA at start-up (verify_taxa): the
scientific_name of one run pulled with tax_eq(<id>) must equal the label in
scope_constants_v3 -- the v1/v2 milk/vaginal errors would have failed this check.

Paging: as in v2, ENA `offset` is unreliable, so every slice is pulled with limit=0 and the
body is parsed in 100k-row chunks into a pyarrow ParquetWriter. Every pull is checked
against the count endpoint.

Modes
  --audit-only   ena_count for every slice; writes enumeration_audit_v3.csv
                 (slice, tag, query, count_v2_if_any, count_v3, ...). No downloads.
  --diff         downloads only the slices that are NEW or CHANGED relative to
                 enumeration_audit_v2.csv (same slice name AND same query = unchanged),
                 aggregates them to study level, and writes
                 universe_v3_delta_studies.parquet (+ _runs.parquet) = studies that are
                 not in catalog_studies.parquet, with enumeration_channels/tags.
  (no flag)      full pull of every slice into enum_v3/ and universe_runs_v3_full.parquet.

Studies surfaced by 'misfiled_genomic' / 'adjudication_other' slices must go through the
triage rubric; nothing in this script decides inclusion.
"""
# --- catalog-pipeline repo layout shim (added 2026-09-26; original ran flat from one cwd) ---
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
import io
import json
import sys
import time
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# (sys.path handled by the repo layout shim above)
import harvest_lib as HL
import scope_constants_v3 as SC

OUT = Path("enum_v3"); OUT.mkdir(exist_ok=True)
CHUNK = 100_000
CATALOG_STUDIES = "catalog_studies.parquet"
AUDIT_V2 = "enumeration_audit_v2.csv"
AUDIT_V3 = "enumeration_audit_v3.csv"

# identical to v1/v2 LEAN_FIELDS (43 columns) so run tables are schema-compatible
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
assert set(LEAN_FIELDS) <= set(SC.ENA_RUN_FIELDS)
RUN_SCHEMA = pa.schema([(c, pa.string()) for c in LEAN_FIELDS]
                       + [("frame_query", pa.string()), ("slice_tag", pa.string())])

SHOT = SC.ena_shotgun_clause()
ADJ = SC.ena_adjudicate_clause()
ALL4 = SC.ena_all_strategies_clause()
MISFILED = SC.ena_misfiled_genomic_clause()

_ROLE_TO_SHOT_TAG = {"primary": "primary_shotgun", "linked": "linked_body_site",
                     "secondary": "secondary_generic", "virome": "virome"}


def build_jobs():
    """[(slice, tag, query)] -- every v2 slice (same names/queries) plus the v3 additions."""
    jobs = []
    for tax in sorted(SC.TAXA_ALL_FRAME_V3):
        shot_tag = _ROLE_TO_SHOT_TAG[SC.TAXON_ROLE[tax]]
        jobs.append((f"tax{tax}_shot", shot_tag, f"tax_eq({tax}) AND {SHOT}"))
        jobs.append((f"tax{tax}_adj", "adjudication_other", f"tax_eq({tax}) AND {ADJ}"))   # (d)
    for name, clause in SC.HOST_FRAME_CLAUSES_V2.items():
        jobs.append((f"{name}_shot", "host_frame", f"{clause} AND {SHOT}"))
        jobs.append((f"{name}_adj", "adjudication_other", f"{clause} AND {ADJ}"))        # (d) incl. tax_eq(9606)
    for tax in sorted(SC.TAXA_MISFILED_FRAME):                                              # (c)
        jobs.append((f"tax{tax}_misfiled", "misfiled_genomic", f"tax_eq({tax}) AND {MISFILED}"))
    assert len({j[0] for j in jobs}) == len(jobs)
    for _, tag, _ in jobs:
        assert tag in SC.SLICE_TAGS, tag
    return jobs


# count-only consistency checks (not pulled)
COUNT_ONLY = {
    "host9606_all4": f"host_tax_id=9606 AND {ALL4}",
    **{f"tax{t}_shot_retired": f"tax_eq({t}) AND {SHOT}" for t in sorted(SC.TAXA_RETIRED)},
    **{f"tax{t}_all_retired": f"tax_eq({t})" for t in sorted(SC.TAXA_RETIRED)},
}


def verify_taxa(taxa=None):
    """Pull one run per frame taxid and check ENA's scientific_name against our label."""
    taxa = taxa or SC.TAXA_ALL_FRAME_V3
    bad = []
    for t, label in sorted(taxa.items()):
        tsv = HL.ena_search("read_run", f"tax_eq({t})", ["run_accession", "scientific_name"],
                            limit=1, purpose="enum_v3_verify_taxa")
        df = pd.read_csv(io.StringIO(tsv), sep="\t", dtype=str) if tsv and tsv.strip() else pd.DataFrame()
        name = df["scientific_name"].iloc[0] if len(df) else None
        if (name or "").lower() != label.lower():
            bad.append((t, label, name))
    if bad:
        raise SystemExit(f"taxid/label mismatch in scope_constants_v3: {bad}")
    print(f"verify_taxa: {len(taxa)} frame taxids match ENA scientific_name", flush=True)


def resolve_taxids(names):
    """scientific_name -> tax_id via a read_run probe (how TAXA_VIROME was resolved)."""
    out = {}
    for nm in names:
        tsv = HL.ena_search("read_run", f'scientific_name="{nm}"', ["run_accession", "tax_id"],
                            limit=5, purpose="enum_v3_resolve")
        df = pd.read_csv(io.StringIO(tsv), sep="\t", dtype=str) if tsv and tsv.strip() else pd.DataFrame()
        ids = sorted(df["tax_id"].unique()) if len(df) else []
        out[nm] = int(ids[0]) if len(ids) == 1 else ids
    return out


def stream_pull(query, tag, slice_tag, fields=LEAN_FIELDS):
    """limit=0 pull, parsed in CHUNK-row pieces straight into enum_v3/<tag>.parquet."""
    expected = HL.ena_count("read_run", query, purpose=f"enum_v3_count:{tag}")
    out_f = OUT / f"{tag}.parquet"
    if expected == 0:
        print(f"  [{tag}] expected 0 -- skipped", flush=True)
        return expected, 0
    t0 = time.time()
    tsv = HL.ena_search("read_run", query, fields, limit=0, purpose=f"enum_v3:{tag}")
    if not tsv or not tsv.strip():
        print(f"  [{tag}] EMPTY body (expected {expected})", flush=True)
        return expected, 0
    got, writer = 0, None
    for chunk in pd.read_csv(io.StringIO(tsv), sep="\t", dtype=str, on_bad_lines="skip",
                             low_memory=False, chunksize=CHUNK, keep_default_na=False):
        for c in fields:
            if c not in chunk:
                chunk[c] = ""
        chunk = chunk[fields].copy()
        chunk["frame_query"] = tag
        chunk["slice_tag"] = slice_tag
        tbl = pa.Table.from_pandas(chunk, schema=RUN_SCHEMA, preserve_index=False)
        if writer is None:
            writer = pq.ParquetWriter(out_f, RUN_SCHEMA, compression="zstd")
        writer.write_table(tbl)
        got += len(chunk)
    if writer:
        writer.close()
    del tsv
    status = "OK" if expected == got else f"MISMATCH (expected {expected})"
    print(f"  [{tag}] rows={got:,} {status} {time.time()-t0:.0f}s", flush=True)
    return expected, got


def load_v2_audit():
    """slice -> (query, count_v2) from enumeration_audit_v2.csv (empty if absent)."""
    try:
        a2 = pd.read_csv(AUDIT_V2)
    except Exception:
        return {}
    return {r.slice: (r.query, int(r.count_v2)) for r in a2.itertuples() if pd.notna(r.count_v2)}


def classify_slices(jobs, v2):
    """new | changed | unchanged relative to v2 (same name AND same query = unchanged)."""
    status = {}
    for tag, _, q in jobs:
        if tag not in v2:
            status[tag] = "new"
        elif v2[tag][0] != q:
            status[tag] = "changed"
        else:
            status[tag] = "unchanged"
    return status


def run_audit(jobs, v2, pulled=None):
    """ena_count every slice + count-only checks; write enumeration_audit_v3.csv."""
    status = classify_slices(jobs, v2)
    pulled = pulled or {}
    rows = []
    for tag, slice_tag, q in jobs:
        c = HL.ena_count("read_run", q, purpose=f"enum_v3_count:{tag}")
        got = pulled.get(tag)
        rows.append({"slice": tag, "tag": slice_tag, "query": q,
                     "count_v2_if_any": v2.get(tag, (None, None))[1], "count_v3": c,
                     "status_vs_v2": status[tag], "got": got,
                     "complete": (got == c) if got is not None else None,
                     "pulled": got is not None})
    for tag, q in COUNT_ONLY.items():
        c = HL.ena_count("read_run", q, purpose=f"enum_v3_count:{tag}")
        rows.append({"slice": tag, "tag": "count_only_check", "query": q,
                     "count_v2_if_any": v2.get(tag, (None, None))[1], "count_v3": c,
                     "status_vs_v2": "count_only", "got": None, "complete": None, "pulled": False})
    audit = pd.DataFrame(rows)
    audit.to_csv(AUDIT_V3, index=False)
    print(f"audit: {len(jobs)} slices + {len(COUNT_ONLY)} count-only checks -> {AUDIT_V3}", flush=True)
    return audit


def union_runs(files, out_path, drop_zero=True):
    """Union slice parquets, dedupe by run, keep ';'-joined provenance of slices and tags."""
    prov, tags = {}, {}
    for f in files:
        t = pq.read_table(f, columns=["run_accession", "frame_query", "slice_tag"]).to_pandas()
        for r, fq, st in zip(t["run_accession"].values, t["frame_query"].values, t["slice_tag"].values):
            prov.setdefault(r, set()).add(fq)
            tags.setdefault(r, set()).add(st)
    schema = pa.schema([(c, pa.string()) for c in LEAN_FIELDS]
                       + [("found_by", pa.string()), ("slice_tags", pa.string())])
    seen = set()
    w = pq.ParquetWriter(out_path, schema, compression="zstd")
    for f in files:
        pf = pq.ParquetFile(f)
        for b in pf.iter_batches(batch_size=CHUNK):
            df = b.to_pandas()
            df = df[~df["run_accession"].isin(seen)]
            if not len(df):
                continue
            seen.update(df["run_accession"].values)
            df["found_by"] = [";".join(sorted(prov[r])) for r in df["run_accession"]]
            df["slice_tags"] = [";".join(sorted(tags[r])) for r in df["run_accession"]]
            df = df.drop(columns=["frame_query", "slice_tag"])
            w.write_table(pa.Table.from_pandas(df, schema=schema, preserve_index=False))
    w.close()
    return len(seen)


def aggregate(runs_path, out_path):
    """Study-level table via aggregate_studies.build (v1 logic) + v3 channel columns."""
    import aggregate_studies as AG
    st = AG.build(runs_path, out_path)
    runs = pd.read_parquet(runs_path, columns=["study_accession", "found_by", "slice_tags"])
    ch = (runs.assign(found_by=runs["found_by"].str.split(";")).explode("found_by")
          .groupby("study_accession")["found_by"].agg(lambda s: ";".join(sorted(set(s)))))
    tg = (runs.assign(slice_tags=runs["slice_tags"].str.split(";")).explode("slice_tags")
          .groupby("study_accession")["slice_tags"].agg(lambda s: ";".join(sorted(set(s)))))
    st["enumeration_channels"] = st["study_accession"].map(ch)
    st["enumeration_tags"] = st["study_accession"].map(tg)
    st["adjudication_only"] = st["enumeration_tags"].apply(
        lambda s: set(s.split(";")) <= SC.ADJUDICATION_TAGS)
    st["scope_version"] = SC.SCOPE_VERSION
    st = st.drop(columns=["found_by"])
    st.to_parquet(out_path, index=False)
    return st


def main(argv):
    audit_only = "--audit-only" in argv
    diff = "--diff" in argv
    verify_taxa()
    jobs = build_jobs()
    v2 = load_v2_audit()

    if audit_only:
        run_audit(jobs, v2)
        return

    status = classify_slices(jobs, v2)
    todo = [j for j in jobs if (not diff) or status[j[0]] != "unchanged"]
    print(f"pulling {len(todo)} of {len(jobs)} slices ({'diff' if diff else 'full'} mode)", flush=True)
    pulled = {}
    for tag, slice_tag, q in todo:
        audit_f = OUT / f"{tag}.audit.json"
        if audit_f.exists():
            a = json.loads(audit_f.read_text())
            if a.get("complete") and ((OUT / f"{tag}.parquet").exists() or a.get("got") == 0):
                pulled[tag] = a["got"]
                continue
        expected, got = stream_pull(q, tag, slice_tag)
        audit_f.write_text(json.dumps({"slice": tag, "tag": slice_tag, "query": q,
                                       "expected": expected, "got": got,
                                       "complete": expected == got}))
        pulled[tag] = got
    audit = run_audit(jobs, v2, pulled)
    inc = audit[(audit.pulled) & (audit.complete == False)]  # noqa: E712
    for r in inc.itertuples():
        print(f"  INCOMPLETE {r.slice}: expected {r.count_v3} got {r.got}", flush=True)

    files = sorted(OUT / f"{t}.parquet" for t in pulled if (OUT / f"{t}.parquet").exists())
    if diff:
        n = union_runs(files, "universe_v3_new_slice_runs.parquet")
        print(f"new/changed-slice unique runs: {n:,}", flush=True)
        st = aggregate("universe_v3_new_slice_runs.parquet", "universe_v3_new_slice_studies.parquet")
        cat = pd.read_parquet(CATALOG_STUDIES, columns=["study_accession"])
        known = set(cat["study_accession"])
        unlinked = st[st["study_accession"].str.strip() == ""]
        if len(unlinked):
            print(f"  runs with EMPTY study_accession dropped from study delta: "
                  f"{int(unlinked['n_runs'].sum())} (recorded in enum_v3/unlinked_runs.json)", flush=True)
            (OUT / "unlinked_runs.json").write_text(unlinked[["n_runs", "enumeration_channels"]].to_json(orient="records"))
        st = st[st["study_accession"].str.strip() != ""]
        delta = st[~st["study_accession"].isin(known)].copy()
        delta["in_catalog_studies"] = False
        delta.to_parquet("universe_v3_delta_studies.parquet", index=False)
        runs = pd.read_parquet("universe_v3_new_slice_runs.parquet")
        druns = runs[runs["study_accession"].isin(set(delta["study_accession"]))]
        if len(druns):
            druns.to_parquet("universe_v3_delta_runs.parquet", index=False)
        print(f"new-slice studies: {len(st):,}; already in catalog: {len(st)-len(delta):,}; "
              f"DELTA (not in catalog): {len(delta):,} studies / {len(druns):,} runs", flush=True)
        print(delta["enumeration_tags"].value_counts().to_string(), flush=True)
    else:
        n = union_runs(files, "universe_runs_v3_full.parquet")
        print(f"UNIQUE runs written: {n:,}", flush=True)
        aggregate("universe_runs_v3_full.parquet", "universe_studies_v3_full.parquet")


if __name__ == "__main__":
    main(sys.argv[1:])

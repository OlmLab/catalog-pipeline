"""gapfill_samples.py — RUNBOOK §3 'new samples in an INCLUDED study' (cycle R2026.2, first run on PRJNA1140720).

Deterministic, cache-through (harvest_lib) build of package-shaped rows for runs/BioSamples that entered an
already-included study after the last package. Steps (each writes to --out):
  1. harvest      ENA browser XML per BioSample (NCBI efetch biosample fallback), study XML, experiment XML
                  -> sample_attributes_new.parquet (sample_key, attr_key, attr_key_norm, value, attr_units, source)
  2. compare      attribute keys / conventions of the new samples vs the study's EXISTING determinations
                  -> attribute_comparison.json
  3. R1           attribute_field_map.csv parsers (r1_parsers), r1_title_parser rows, unit resolution
                  U1/U2 (r1_prime.resolve_units) + U3 (a linked paper's per-individual supplementary table whose
                  age column header names the unit and agrees with the bare attribute for >= 90 % of matched
                  samples), composite subject ids when the study's existing subject_id convention is
                  <family_id>_<subjectid> and the library name carries it
     R2           supplementary tables of own-data papers linked in study_paper_links.csv: exact-ID gate
                  (BioSample / run / experiment / library name / title; >= 50 % rows or >= 20 exact matches);
                  header-named columns only (deterministic — no LLM column classification)
     R3/R4        never minted here; existing cohort_default group rows of the study are extended verbatim
                  -> sample_determinations_new.parquet, *_superseded, *_sentinels, r2_gate.csv, unit_rules.csv
  4. subjects     subject_resolution.resolve on the new rows; subject_key / linked_infant_subject_key joined to the
                  study's existing subjects -> sample_subjects_new.parquet
  5. sandpiper    optional (--sandpiper): per-run API metadata + condensed_csv_with_extras at <= 0.5 req/s;
                  runs absent from Sandpiper get sp_miss_reason from the snapshot horizon
                  -> sandpiper_run_qc_new.parquet, sandpiper_sample_summary_new.parquet
  6. outputs      runs_new.parquet, samples_new_wide.parquet (package column set, build_wide logic + derived scope
                  columns), study_metadata_wide_delta.json, GAPFILL_<study>_REPORT.md
Every committed value carries a labelled evidence source and passes curation_kernel_ext.validate_row; ages > 1,100 d
are committed under the v1.2 `out_of_scope_adult` convention (evidence for adult_age_flag) and counted separately.
Usage: python -m catalog.extraction.gapfill_samples --study PRJNA1140720 --new-runs new_runs.parquet \
         --package data/inputs/data_package --out build/gapfill_R2026.2 --release-id R2026.2 --package-version 1.4.0 \
         [--field-map config/attribute_field_map.csv] [--cache-dir ~/catalog/cache] [--sandpiper] [--harvest-existing]
"""
# --- microbiome_repo-pipeline repo layout shim ---
import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__)) if "__file__" in globals() else _os.getcwd()
for _p in (_here, _os.path.join(_here, "..", ".."), _os.path.join(_here, "..", "harvest"), _os.path.join(_here, "..", "enumeration"),
           _os.path.join(_here, "..", "triage"), _os.path.join(_here, "..", "sandpiper")):
    _p = _os.path.abspath(_p)
    if _p not in _sys.path:
        _sys.path.insert(0, _p)
try:
    from catalog.models import resolve_model, set_host
except ImportError:
    from models import resolve_model, set_host
set_host(globals().get("host"))
# -----------------------------------------
import argparse, io, json, os, re, time, zipfile
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd

import r1_parsers as P
import r1_prime
from r1_title_parser import parse_sample_name, FACT
import subject_resolution as SR
import build_wide as BW
import curation_kernel_ext as K
import scope_constants_ext as SCX

TARGET_FIELDS = list(SCX.TARGET_FIELDS_EXT)
ALL_FIELDS = TARGET_FIELDS + ["sex", "timepoint_label", "subject_id"]
DET_COLS = ["sample_key", "field_name", "study_accession", "field_value", "value_normalized", "confidence", "evidence_source",
            "evidence_locator", "evidence_quote", "evidence_limited_to_abstract", "determined_by", "route", "scope", "parse_note",
            "group_audit", "src_track", "release_added", "release_retired", "package_added"]
ENA_XML = "https://www.ebi.ac.uk/ena/browser/api/xml/"
SANDPIPER_API = "https://sandpiper.qut.edu.au/api/"
SNAPSHOT_HORIZON = "2026-03-22"     # Zenodo 20419175 / Sandpiper 2.0.0 (SANDPIPER_REPORT.md)
UNIT_TOKEN = {"day": "days", "days": "days", "week": "weeks", "weeks": "weeks", "month": "months", "months": "months", "year": "years", "years": "years"}


def q12(s):
    return " ".join(str(s).split()[:12])[:200]


def norm_key(k):
    return re.sub(r"[^a-z0-9]+", "_", str(k).lower()).strip("_")


def log(msg):
    print(f"[gapfill] {msg}", flush=True)


# ------------------------------------------------------------------------------------------------ 1. harvest
def _hl():
    import harvest_lib as HL
    import harvest_samples as HS
    return HL, HS


def harvest(study, new_runs, purpose="gapfill"):
    HL, HS = _hl()
    keys = sorted(new_runs.sample_accession.dropna().unique())
    urls = [ENA_XML + ",".join(keys[i:i + 50]) for i in range(0, len(keys), 50)]
    res = HL.fetch_many(urls, purpose=f"{purpose}_sample_xml", workers=3)
    rows, seen, n_err = [], set(), 0
    for u, r in res.items():
        if r.get("ok") and r.get("body"):
            rr, ss = HS.parse_ena(r["body"]); rows += rr; seen |= ss
        else:
            n_err += 1
    missing = [k for k in keys if k not in seen]
    n_ncbi = 0
    if missing:  # ENA often 404s for 2025-26 SAMN records -> NCBI BioSample
        for txt in HL.efetch("biosample", missing, purpose=f"{purpose}_ncbi_biosample", batch=100):
            if txt.get("ok"):
                rr, ss = HS.parse_ncbi(txt["body"]); rows += rr; seen |= ss
        n_ncbi = len([k for k in missing if k in seen])
    attrs = pd.DataFrame(rows, columns=HS.COLS).rename(columns={"attr_value": "value"})
    st = HL.fetch(ENA_XML + study, purpose=f"{purpose}_study_xml")
    study_meta = {}
    if st.get("ok"):
        root = ET.fromstring(st["body"])
        study_meta = dict(title=root.findtext(".//STUDY_TITLE") or root.findtext(".//TITLE"),
                          description=root.findtext(".//STUDY_ABSTRACT") or root.findtext(".//STUDY_DESCRIPTION") or root.findtext(".//DESCRIPTION"))
    exps = sorted(new_runs.experiment_accession.dropna().unique())
    xres = HL.fetch_many([ENA_XML + ",".join(exps[i:i + 50]) for i in range(0, len(exps), 50)], purpose=f"{purpose}_experiment_xml", workers=3)
    xrows = []
    for u, r in xres.items():
        if r.get("ok"):
            for e in ET.fromstring(r["body"]).iter("EXPERIMENT"):
                sd = e.find(".//SAMPLE_DESCRIPTOR")
                xrows.append(dict(experiment_accession=e.get("accession"), exp_alias=e.get("alias"), exp_title=e.findtext("TITLE"),
                                  library_name=e.findtext(".//LIBRARY_NAME"), library_strategy=e.findtext(".//LIBRARY_STRATEGY"),
                                  library_source=e.findtext(".//LIBRARY_SOURCE"), sample_ref=sd.get("accession") if sd is not None else None,
                                  design=e.findtext(".//DESIGN_DESCRIPTION")))
    exps_df = pd.DataFrame(xrows)
    stats = dict(n_samples=len(keys), n_found=len(seen), n_ena=len(seen) - n_ncbi, n_ncbi=n_ncbi, n_missing=len(keys) - len(seen),
                 n_ena_batches_err=n_err, n_attr_rows=len(attrs), n_experiments=len(exps_df))
    return attrs, exps_df, study_meta, stats


def harvest_existing(sample_keys, purpose="gapfill_existing"):
    HL, HS = _hl()
    keys = sorted(sample_keys)
    res = HL.fetch_many([ENA_XML + ",".join(keys[i:i + 50]) for i in range(0, len(keys), 50)], purpose=f"{purpose}_sample_xml", workers=3)
    rows, seen = [], set()
    for u, r in res.items():
        if r.get("ok") and r.get("body"):
            rr, ss = HS.parse_ena(r["body"]); rows += rr; seen |= ss
    missing = [k for k in keys if k not in seen]
    if missing:
        for txt in HL.efetch("biosample", missing, purpose=f"{purpose}_ncbi", batch=100):
            if txt.get("ok"):
                rr, ss = HS.parse_ncbi(txt["body"]); rows += rr; seen |= ss
    return pd.DataFrame(rows, columns=HS.COLS).rename(columns={"attr_value": "value"})


# ------------------------------------------------------------------------------------------------ 2. compare
def compare_with_existing(study, det0, wide0, subj0, attrs, existing_attrs=None):
    d = det0[det0.study_accession == study]
    out = dict(study=study, n_existing_samples=int(len(wide0)), n_new_samples=int(attrs.sample_key.nunique()))
    out["existing_determinations"] = {f"{r.field_name}|{r.route}|{r.evidence_source}|{r.evidence_locator}": int(r.n)
                                      for r in d.groupby(["field_name", "route", "evidence_source", "evidence_locator"]).size().rename("n").reset_index().itertuples()}
    out["existing_wide"] = {c: {str(k): int(v) for k, v in wide0[c].value_counts(dropna=False).items()}
                            for c in ("body_site_class", "age_scope", "catalog_scope", "role", "role_source", "adult_age_flag", "sample_unit") if c in wide0}
    out["existing_group_rows_cohort_default"] = int((d.evidence_source == "cohort_default").sum() + d.scope.astype(str).str.startswith("group").sum())
    new_keys = attrs.groupby("attr_key_norm").sample_key.nunique().to_dict()
    out["new_attribute_keys"] = {k: int(v) for k, v in new_keys.items()}
    if existing_attrs is not None and len(existing_attrs):
        ek = existing_attrs.groupby("attr_key_norm").sample_key.nunique().to_dict()
        out["existing_attribute_keys"] = {k: int(v) for k, v in ek.items()}
        out["keys_only_in_new"] = sorted(set(new_keys) - set(ek))
        out["keys_only_in_existing"] = sorted(set(ek) - set(new_keys))
        for k in ("participant_type", "sample_type", "isolation_source", "organism", "host", "title"):
            if k in ek or k in new_keys:
                out.setdefault("value_shift", {})[k] = dict(
                    existing=existing_attrs[existing_attrs.attr_key_norm == k].value.value_counts().head(8).to_dict(),
                    new=attrs[attrs.attr_key_norm == k].value.value_counts().head(8).to_dict())
    return out


# ------------------------------------------------------------------------------------------------ 3. R1
def _field_map_rows(study, attrs, fm, unit_for=None):
    """Port of r1_run.run_det for the deterministic parsers of attribute_field_map.csv (haiku/SKIP rows skipped)."""
    out, rejected = [], []

    def emit(sk, key, field, raw, norm, conf, note):
        row = dict(sample_key=sk, field_name=field, study_accession=study, field_value=str(raw)[:120], value_normalized=norm, confidence=float(conf),
                   evidence_source=f"sample.attr.{key}", evidence_locator=key, evidence_quote=q12(f"{key}={str(raw)[:80]}"), evidence_limited_to_abstract=0.0,
                   determined_by="deterministic_r1", route="R1", scope="sample", parse_note=note, group_audit=None, src_track="gapfill_r1")
        (out if norm is not None else rejected).append(row)

    for m in fm[~fm.parser.isin(["haiku", "SKIP"])].itertuples(index=False):
        key, field, parser, conf = m.attr_key_norm, m.field_name, m.parser, m.confidence
        unit = None if (m.unit_default is None or (isinstance(m.unit_default, float) and np.isnan(m.unit_default))) else m.unit_default
        sub = attrs[attrs.attr_key_norm == key]
        if sub.empty:
            continue
        for sk, v in zip(sub.sample_key, sub.value):
            s = str(v).strip()
            if P.is_null(s):
                continue
            if parser in ("age_text_unitkey", "age_numeric"):
                if re.fullmatch(P.NUM, s):
                    u = (unit_for(sk, key) if unit_for else None) or unit
                    if u is None:
                        emit(sk, key, field, v, None, conf, "bare number, no unit key"); continue
                    d = P.to_days(float(s), u)
                    emit(sk, key, field, v, None if d is None else round(d), conf, f"unit_key {u}")
                else:
                    d, note = P.parse_age_text(s); emit(sk, key, field, v, d, conf, note)
                    if re.search(r"pre-?term|prematur", s, re.I):
                        emit(sk, key, "preterm_status", v, "preterm", 0.85, "age text says premature")
                continue
            if parser == "age_text": norm, note = P.parse_age_text(s)
            elif parser in ("ga_numeric", "ga_wplusd"): norm, note = P.parse_ga(s, unit)
            elif parser == "bw_numeric": norm, note = P.parse_bw(s)
            elif parser == "categorical_delivery": norm, note = P.parse_delivery(s, key)
            elif parser == "categorical_feeding": norm, note = P.parse_feeding(s, key)
            elif parser == "percent_feeding": norm, note = P.parse_percent_feeding(s, key)
            elif parser == "categorical_yesno": norm, note = P.parse_yesno(s, key)
            elif parser == "categorical_sex": norm, note = P.parse_sex(s, key)
            elif parser == "categorical_nec": norm, note = P.parse_nec(s, key)
            elif parser == "categorical_hmo": norm, note = P.parse_hmo(s, key)
            elif parser == "categorical_probiotic_freq": norm, note = P.parse_probiotic_freq(s, key)
            elif parser == "categorical": norm, note = P.parse_preterm_coded(s, key)
            elif parser == "country": norm, note = P.parse_country(s)
            elif parser in ("identifier", "label"): norm, note = (str(s).strip(), parser)
            elif parser == "babyid_dol":
                mm = re.fullmatch(r"([A-Za-z]+\d+)_(\d+)", s)
                norm, note = ((int(mm.group(2)) if field == "age_at_collection_days" else mm.group(1)), parser) if mm else (None, "unparsed")
            elif parser == "phenotype_age_sex":
                mm = re.match(r"(female|male)_subject_of_(\d+(?:\.\d+)?)_years", s)
                norm, note = ((round(float(mm.group(2)) * 365.25), "phenotype") if mm else (None, "unparsed")) if field == "age_at_collection_days" else P.parse_sex(s, key)
            else:
                norm, note = None, "no parser"
            if note == "null":
                continue
            emit(sk, key, field, v, None if norm is None else str(norm), conf, note)
    return pd.DataFrame(out, columns=DET_COLS), pd.DataFrame(rejected, columns=DET_COLS)


def _supp_id_columns(df):
    """Header row + candidate id columns of a supplementary sheet (first non-empty row as header)."""
    if df.empty:
        return None, None
    hdr_i = next((i for i in range(min(5, len(df))) if df.iloc[i].notna().sum() >= max(2, 0.5 * df.shape[1])), 0)
    body = df.iloc[hdr_i + 1:].copy(); body.columns = [str(c).strip() for c in df.iloc[hdr_i].tolist()]
    return body, hdr_i


def resolve_units_u3(rej_age, attrs, supp_sheets, min_matched=20, agree=0.75):
    """U3: a linked paper's per-individual/per-sample table has an age column whose HEADER names the unit
    (age_months, age_years, age_in_days ...). Join rows to samples on an exact id match (BioSample, run, library name,
    or the study's subject attribute — raw or its digit token). Adopt unit u for the bare attribute when
    value*FACT[u] agrees with the table's age (in days) within 0.5 unit for >= `agree` of >= `min_matched` samples,
    and the join is corroborated by at least one further shared column (type/family/sex) agreeing >= 95 %.
    The study-level fraction (default 0.75) only guards against a coincidental table match: ONLY the individually agreeing
    samples are committed (returned as the third element); disagreeing samples stay sentinels (mixed-unit trap).
    Returns (unit or None, rule table rows, set of corroborated sample_keys)."""
    rules = []
    if rej_age.empty or not supp_sheets:
        return None, rules, set()
    # small deltas (< 20 bare-age samples) cannot reach the pooled-table gate; require every bare-age sample instead (floor 3)
    min_matched = max(3, min(min_matched, int(rej_age.sample_key.nunique())))
    sid_attrs = attrs[attrs.attr_key_norm.isin(SR.SUBJECT_KEYS)][["sample_key", "attr_key_norm", "value"]]
    sid_attrs = sid_attrs.assign(tok=sid_attrs.value.astype(str).str.extract(r"(\d+)$")[0])
    other = attrs[attrs.attr_key_norm.isin(SR.ROLE_KEYS + SR.FAMILY_KEYS + ["sex"])].pivot_table(index="sample_key", columns="attr_key_norm", values="value", aggfunc="first")
    vals = rej_age.assign(v=pd.to_numeric(rej_age.field_value, errors="coerce")).dropna(subset=["v"])
    for (fname, sheet), raw in supp_sheets.items():
        body, hdr_i = _supp_id_columns(raw)
        if body is None or len(body) < min_matched:
            continue
        age_cols = [c for c in body.columns if re.fullmatch(r"age[_ ]?(?:in[_ ]?|at[_ ]?\w+[_ ]?)?(days?|weeks?|months?|years?)", norm_key(c).replace("_", " "), re.I)
                    or re.fullmatch(r"age_(days?|weeks?|months?|years?)", norm_key(c))]
        if not age_cols:
            continue
        for idc in body.columns:
            col = body[idc].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
            # exact join on sample attribute id, else on its digit token
            for how, keycol in (("subject_attr_exact", "value"), ("subject_attr_digits", "tok")):
                lk = sid_attrs[["sample_key", keycol]].dropna().astype(str).rename(columns={keycol: "_id"})
                if col.isin(set(lk._id)).sum() < 3:
                    continue
                # one table row -> every sample of that subject
                j = body.assign(_id=col).merge(lk, on="_id", how="inner")
                j = vals.merge(j, on="sample_key", how="inner")
                if len(j) < min_matched:
                    continue
                for ac in age_cols:
                    mu = re.search(r"(day|week|month|year)", norm_key(ac))
                    if not mu:
                        continue
                    tu = UNIT_TOKEN[mu.group(1) + "s"]
                    tdays = pd.to_numeric(j[ac], errors="coerce") * FACT[tu]
                    ok_any, ok_frac, ok_samples = None, 0.0, set()
                    for u in ("days", "weeks", "months", "years"):
                        d = (j.v * FACT[u] - tdays).abs() <= 0.5 * FACT[u] + 0.5 * FACT[tu]
                        frac = float(d[tdays.notna()].mean()) if tdays.notna().any() else 0.0
                        rules.append(dict(sheet=f"{fname}[{sheet}]", id_column=idc, join=how, age_column=ac, table_unit=tu, candidate_unit=u,
                                          n_matched=int(tdays.notna().sum()), frac_agree=round(frac, 3)))
                        if frac >= agree:
                            ok_any, ok_frac, ok_samples = u, frac, set(j.sample_key[d & tdays.notna()])
                    if ok_any:
                        # corroboration: another shared column agrees
                        corr = None
                        for oc in body.columns:
                            k = norm_key(oc)
                            if k in other.columns and k != norm_key(ac):
                                a = j[oc].astype(str).str.strip().str.lower(); b = j.sample_key.map(other[k]).astype(str).str.strip().str.lower()
                                if (a == b).mean() >= 0.95:
                                    corr = k; break
                        if corr:
                            ev = f"paper.supp.{fname}[{sheet}!{ac}] {idc} join ({how}); {corr} agrees; n={int(tdays.notna().sum())} agree={ok_frac:.3f}"
                            return ok_any, rules + [dict(sheet=f"{fname}[{sheet}]", id_column=idc, join=how, age_column=ac, table_unit=tu, candidate_unit=ok_any, n_matched=int(tdays.notna().sum()), frac_agree=round(ok_frac, 3), adopted=True, corroboration=corr, evidence=ev, n_samples_corroborated=len(ok_samples))], ok_samples
    return None, rules, set()


def composite_subject_rows(study, new_runs, attrs, subj0):
    """When the study's existing subject ids follow <family_id>_<subjectid> and the run library name carries that
    composite, emit subject_id from run.library_name (sample_id_pattern) so subject_key joins the existing subjects."""
    fam = attrs[attrs.attr_key_norm.isin(SR.FAMILY_KEYS)].drop_duplicates("sample_key").set_index("sample_key").value
    sid = attrs[attrs.attr_key_norm.isin(SR.SUBJECT_KEYS)].drop_duplicates("sample_key").set_index("sample_key").value
    if fam.empty or sid.empty or subj0.empty:
        return pd.DataFrame(columns=DET_COLS), {}
    comp = (fam.astype(str) + "_" + sid.astype(str)).dropna()
    ex_ids = set(subj0.subject_id_resolved.dropna().astype(str))
    lib = new_runs.drop_duplicates("sample_accession").set_index("sample_accession").library_name.reindex(comp.index)
    in_lib = pd.Series([isinstance(l, str) and re.search(r"(?<![A-Za-z0-9])" + re.escape(c) + r"(?![A-Za-z0-9])", l) is not None for c, l in zip(comp, lib)], index=comp.index)
    frac_existing = float(comp.isin(ex_ids).mean())
    stats = dict(n_composite=int(len(comp)), frac_matching_existing_subject_ids=round(frac_existing, 4), n_in_library_name=int(in_lib.sum()))
    if frac_existing < 0.5 or in_lib.mean() < 0.5:
        return pd.DataFrame(columns=DET_COLS), stats
    fam_key = attrs[attrs.attr_key_norm.isin(SR.FAMILY_KEYS)].drop_duplicates("sample_key").set_index("sample_key").attr_key_norm
    sid_key = attrs[attrs.attr_key_norm.isin(SR.SUBJECT_KEYS)].drop_duplicates("sample_key").set_index("sample_key").attr_key_norm
    rows = [dict(sample_key=sk, field_name="subject_id", study_accession=study, field_value=f"{fam_key[sk]}={fam[sk]}; {sid_key[sk]}={sid[sk]}"[:120], value_normalized=comp[sk], confidence=0.85,
                 evidence_source=f"sample.attr.{sid_key[sk]}", evidence_locator=f"{fam_key[sk]}+{sid_key[sk]}", evidence_quote=q12(f"{fam_key[sk]}={fam[sk]} {sid_key[sk]}={sid[sk]}"), evidence_limited_to_abstract=0.0,
                 determined_by="gapfill_composite_subject", route="R1", scope="sample",
                 parse_note=(f"family_subject_composite: <{fam_key[sk]}>_<{sid_key[sk]}> = the study's existing subject_id convention ({frac_existing:.0%} of composites match existing subjects; "
                             f"run.library_name carries the composite for {int(in_lib.sum())}/{len(comp)}" + ("" if in_lib[sk] else "; not in this library name") + ")"),
                 group_audit=None, src_track="gapfill_r1") for sk in comp.index]
    return pd.DataFrame(rows, columns=DET_COLS), stats


def extend_group_rows(study, det0, new_keys):
    """Extend existing R3/R4 cohort_default (group-scope) statements of the study to the new samples verbatim."""
    g = det0[(det0.study_accession == study) & ((det0.evidence_source == "cohort_default") | det0.scope.astype(str).str.startswith("group"))]
    if g.empty:
        return pd.DataFrame(columns=DET_COLS)
    tmpl = g.drop_duplicates(["field_name", "evidence_source", "evidence_quote", "value_normalized"])
    rows = []
    for t in tmpl.itertuples(index=False):
        for sk in new_keys:
            r = t._asdict(); r["sample_key"] = sk; r["parse_note"] = f"{r.get('parse_note') or ''} | extended to gapfill samples (cohort_default)".strip(" |")
            rows.append(r)
    return pd.DataFrame(rows)[DET_COLS]


def validate_all(det):
    """validate_row on every committed row. Out-of-range ages (> 1,100 d) are committed under the v1.2
    out_of_scope_adult convention and flagged; everything else must pass. Returns (accepted, rejected, n_oos_adult)."""
    ok, msgs, oos = [], [], []
    for r in det.itertuples(index=False):
        row = {"record_id": r.sample_key, "slot": r.field_name, "value": r.value_normalized, "outcome": "resolved_from_raw",
               "confidence": float(r.confidence), "evidence": [{"source": r.evidence_source, "quote": q12(r.evidence_quote)}], "model": r.determined_by}
        good, msg = K.validate_row(row)
        is_oos = False
        if good and r.field_name == "age_at_collection_days":
            # Rule 10: the day value must lie in 0-1100 for an in-scope infant sample; > 1100 d is committed under the
            # v1.2 out_of_scope_adult convention (adult_age_flag evidence), < 0 / unparseable is rejected
            ok_a, msg_a, d = K.validate_age(r.value_normalized, "days")
            if not ok_a:
                if d is not None and d > 1100:
                    is_oos = True; msg = f"out_of_scope_adult | validate_age: {msg_a}"
                else:
                    good, msg = False, msg_a
        ok.append(good); msgs.append(msg); oos.append(is_oos)
    ok = np.array(ok, dtype=bool); oos = np.array(oos, dtype=bool)
    det = det.copy()
    det.loc[oos, "parse_note"] = [f"{m} | {p}" for m, p in zip(np.array(msgs, dtype=object)[oos], det.loc[oos, "parse_note"].astype(str))]
    rej = det[~ok].copy(); rej["reject_reason"] = np.array(msgs, dtype=object)[~ok]
    return det[ok].copy(), rej, int(oos.sum())


def r1_extract(study, new_runs, attrs, fm, det0, subj0, supp_sheets, release_id, package_version):
    smp = new_runs.drop_duplicates("sample_accession").rename(columns={"sample_accession": "sample_key"})[["sample_key", "study_accession", "sample_title", "library_name"]]
    base, rej = _field_map_rows(study, attrs, fm)
    # unit resolution for bare numeric ages: U1/U2 (r1_prime) then U3 (paper table)
    rej_age = rej[(rej.field_name == "age_at_collection_days") & rej.parse_note.str.contains("bare number")]
    unit_rows, rules_tab, unresolved = pd.DataFrame(), pd.DataFrame(), []
    u3_rules = []
    if len(rej_age):
        rj = rej_age.assign(reject_reason=rej_age.parse_note, attr_value=rej_age.field_value)
        at = attrs.rename(columns={"value": "attr_value"})
        unit_rows, rules_tab, unresolved = r1_prime.resolve_units(rj, at, smp)
        if len(unit_rows):
            unit_rows["evidence_source"] = "sample.attr." + unit_rows.evidence_locator.astype(str)
            unit_rows["evidence_quote"] = unit_rows.evidence_locator.astype(str) + "=" + unit_rows.field_value.astype(str)
        if unresolved:
            u3_unit, u3_rules, u3_ok = resolve_units_u3(rej_age, attrs, supp_sheets)
            if u3_unit:
                ev = [r for r in u3_rules if r.get("adopted")][-1]["evidence"]
                rows = []
                for r in rej_age.itertuples(index=False):
                    v = pd.to_numeric(r.field_value, errors="coerce")
                    if pd.isna(v) or r.sample_key not in u3_ok:   # per-sample corroboration: a disagreeing sample stays a sentinel
                        continue
                    rows.append(dict(sample_key=r.sample_key, field_name="age_at_collection_days", study_accession=study, field_value=r.field_value,
                                     value_normalized=str(int(round(v * FACT[u3_unit]))), confidence=0.85, evidence_source=r.evidence_source, evidence_locator=r.evidence_locator,
                                     evidence_quote=r.evidence_quote, evidence_limited_to_abstract=0.0, determined_by="r1_unit_resolution_gapfill", route="R1", scope="sample",
                                     parse_note=f"unit_resolved:U3:{u3_unit}: {ev}"[:400], group_audit=None, src_track="gapfill_r1"))
                unit_rows = pd.concat([unit_rows, pd.DataFrame(rows)], ignore_index=True)
    trows = r1_prime.title_rows(smp)
    if len(trows):
        trows = trows.assign(evidence_source=trows.evidence_source.replace({"sample.library_name": "run.library_name"}), evidence_limited_to_abstract=0.0,
                             scope="sample", group_audit=None, src_track="gapfill_r1")
    comp_rows, comp_stats = composite_subject_rows(study, new_runs, attrs, subj0)
    grp = extend_group_rows(study, det0, list(smp.sample_key))
    parts = [x for x in (base, unit_rows, trows, comp_rows, grp) if x is not None and len(x)]
    det = pd.concat(parts, ignore_index=True).reindex(columns=DET_COLS)
    det = det[det.value_normalized.notna()]
    det["value_normalized"] = det.value_normalized.astype(str)
    # compact-letter title ages are never committed (r1_prime policy) — title_rows already drops them
    # precedence within R1: composite subject id > attribute > title parser ; ties by confidence
    prio = det.determined_by.map({"gapfill_composite_subject": 0, "deterministic_r1": 1, "r1_unit_resolution": 1, "r1_unit_resolution_gapfill": 1, "r1_title_parser": 2}).fillna(3)
    det = det.assign(_p=prio).sort_values(["sample_key", "field_name", "_p", "confidence"], ascending=[True, True, True, False])
    keep = ~det.duplicated(["sample_key", "field_name"], keep="first")
    superseded = det[~keep].drop(columns="_p").copy(); det = det[keep].drop(columns="_p").copy()
    det, rejected, n_oos = validate_all(det)
    rej = rej.copy()
    if len(rej_age) and len(u3_rules) and any(r.get("adopted") for r in u3_rules):
        m = (rej.field_name == "age_at_collection_days") & rej.parse_note.str.contains("bare number")
        rej.loc[m, "parse_note"] = rej.loc[m, "parse_note"] + " | U3 unit adopted for the study but this sample's value disagrees with the paper table"
    rejected = pd.concat([rejected, rej.assign(reject_reason=rej.parse_note)], ignore_index=True)
    have_now = set(zip(det.sample_key, det.field_name))
    rejected = rejected[[(a, b) not in have_now for a, b in zip(rejected.sample_key, rejected.field_name)]]  # resolved later (unit rules)
    det["release_added"] = release_id; det["release_retired"] = None; det["package_added"] = package_version
    det["evidence_limited_to_abstract"] = det.evidence_limited_to_abstract.fillna(0.0).astype(float)
    # sentinels for every (sample, field) without a committed value
    have = set(zip(det.sample_key, det.field_name))
    sent = [dict(K.sentinel_row(sk, f, "gapfill_samples", note="no R1 evidence; no R2 source" if f in TARGET_FIELDS else "no R1 evidence"), study_accession=study)
            for sk in smp.sample_key for f in ALL_FIELDS if (sk, f) not in have]
    sentinels = pd.DataFrame(sent)
    meta = dict(n_committed=int(len(det)), n_superseded=int(len(superseded)), n_rejected=int(len(rejected)), n_out_of_scope_adult=n_oos,
                n_sentinels=int(len(sentinels)), unit_rules=rules_tab.to_dict("records") if len(rules_tab) else [], unit_unresolved=unresolved,
                u3_rules=u3_rules, composite_subject=comp_stats, n_group_rows_extended=int(len(grp)),
                fields_committed={k: int(v) for k, v in det.field_name.value_counts().items()})
    return det.reset_index(drop=True), superseded.reset_index(drop=True), rejected.reset_index(drop=True), sentinels, meta


# ------------------------------------------------------------------------------------------------ R2 gate
def r2_gate(study, pkg, new_runs, purpose="gapfill_r2"):
    """Fetch supplementary ZIPs of own-data papers linked to the study; return (gate table, sheets dict)."""
    HL, _ = _hl()
    links = pd.read_csv(os.path.join(pkg, "study_paper_links.csv"))
    links = links[(links.study_accession == study) & links.pmcid.notna()]
    ids = set(new_runs.sample_accession.dropna()) | set(new_runs.run_accession) | set(new_runs.library_name.dropna()) | set(new_runs.secondary_sample_accession.dropna()) | set(new_runs.experiment_accession.dropna()) | set(new_runs.sample_title.dropna())
    n_new = new_runs.sample_accession.nunique()
    gate, sheets = [], {}
    for pm in links.pmcid.unique():
        z = HL.epmc_supplementary_zip(pm, purpose=purpose)
        if not (z.get("ok") and z.get("body")):
            gate.append(dict(pmcid=pm, file=None, sheet=None, status=z.get("status"), note="no supplementary zip")); continue
        try:
            zf = zipfile.ZipFile(io.BytesIO(z["body"]))
        except zipfile.BadZipFile:
            gate.append(dict(pmcid=pm, file=None, sheet=None, status=z.get("status"), note="bad zip")); continue
        for n in zf.namelist():
            if not n.lower().endswith((".xlsx", ".xls", ".csv", ".tsv", ".txt")):
                continue
            try:
                if n.lower().endswith((".xlsx", ".xls")):
                    sh = pd.read_excel(io.BytesIO(zf.read(n)), sheet_name=None, header=None, dtype=str)
                else:
                    sh = {"": pd.read_csv(io.BytesIO(zf.read(n)), sep=None, engine="python", header=None, dtype=str)}
            except Exception as e:  # noqa: BLE001
                gate.append(dict(pmcid=pm, file=n, sheet=None, note=f"unreadable: {e}"[:120])); continue
            for s, df in sh.items():
                cells = df.stack().dropna().astype(str).str.strip()
                hits = cells[cells.isin(ids)]
                n_hit = int(hits.nunique())
                # exact-ID gate: >= 50 % of table rows or >= 20 exact matches; matrix-shaped sheets (ids in header
                # AND first column, numeric body) carry no metadata columns
                body, hdr_i = _supp_id_columns(df)
                is_matrix = body is not None and df.shape[1] > 20 and df.iloc[0].astype(str).isin(ids).sum() > 0 and pd.to_numeric(body.iloc[:, 1:].stack(), errors="coerce").notna().mean() > 0.9
                passes = (n_hit >= 20) or (len(df) > 1 and n_hit / max(1, len(df) - 1) >= 0.5)
                named_cols = [c for c in (body.columns if body is not None else []) if norm_key(c) in set(FM_KEYS)] if body is not None else []
                gate.append(dict(pmcid=pm, file=n, sheet=s, n_rows=int(len(df)), n_cols=int(df.shape[1]), n_exact_id_hits=n_hit, frac_new_ids_hit=round(n_hit / max(1, n_new), 3),
                                 passes_exact_gate=bool(passes), is_matrix=bool(is_matrix), header_named_field_columns=";".join(named_cols[:10]),
                                 r2_usable=bool(passes and not is_matrix and named_cols)))
                sheets[(n, s)] = df
    return pd.DataFrame(gate), sheets


FM_KEYS = []  # filled from the field map at runtime (attribute keys that name a target field)


def r2_extract(study, gate, sheets, new_runs, fm, release_id, package_version):
    """Header-named columns of gate-passing, non-matrix sheets, joined on exact ids (BioSample/run/library/title)."""
    rows = []
    if gate.empty:
        return pd.DataFrame(columns=DET_COLS)
    key_of = {}
    for r in new_runs.drop_duplicates("sample_accession").itertuples(index=False):
        for v in (r.sample_accession, r.run_accession, r.library_name, r.secondary_sample_accession, r.experiment_accession, r.sample_title):
            if isinstance(v, str) and v:
                key_of.setdefault(v, r.sample_accession)
    for g in gate[gate.r2_usable.fillna(False)].itertuples(index=False):
        df = sheets[(g.file, g.sheet)]; body, _ = _supp_id_columns(df)
        idc = next((c for c in body.columns if body[c].astype(str).str.strip().isin(key_of).mean() >= 0.5), None)
        if idc is None:
            continue
        sub = body.assign(_sk=body[idc].astype(str).str.strip().map(key_of)).dropna(subset=["_sk"])
        fmk = fm.set_index("attr_key_norm")
        for c in body.columns:
            k = norm_key(c)
            if k not in fmk.index or c == idc:
                continue
            m = fmk.loc[[k]].iloc[0]
            if m.parser in ("haiku", "SKIP"):
                continue
            tmp = pd.DataFrame(dict(sample_key=sub._sk.values, attr_key=[c] * len(sub), attr_key_norm=[k] * len(sub), value=sub[c].values, attr_units=None, source="paper_supp"))
            d, _ = _field_map_rows(study, tmp, fm.loc[fm.attr_key_norm == k])
            if len(d):
                d["evidence_source"] = f"paper.supp.{os.path.basename(g.file)}[{g.sheet}!{c}]"; d["route"] = "R2"; d["determined_by"] = "gapfill_r2_header_named"
                d["src_track"] = "gapfill_r2"; d["parse_note"] = d.parse_note + f" | exact id join on {idc}"
                rows.append(d)
    out = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=DET_COLS)
    if len(out):
        out["release_added"] = release_id; out["release_retired"] = None; out["package_added"] = package_version
    return out


# ------------------------------------------------------------------------------------------------ 4. subjects
def build_subjects(study, det, new_runs, attrs, subj0, body_site_class):
    smp = new_runs.drop_duplicates("sample_accession").rename(columns={"sample_accession": "sample_key"})
    A = attrs.pivot_table(index="sample_key", columns="attr_key_norm", values="value", aggfunc="first")
    bsr = A.reindex(columns=["isolation_source", "sample_type", "body_site", "env_medium", "organism"]).astype(object).where(lambda x: x.notna(), None)
    body_raw = bsr.apply(lambda r: next((v for v in r if isinstance(v, str) and v.strip()), None), axis=1)
    sam = pd.DataFrame(dict(sample_key=smp.sample_key.values, study_accession=study, sample_title=smp.sample_title.values, library_name=smp.library_name.values,
                            body_site_raw=smp.sample_key.map(body_raw).values, body_site_class=smp.sample_key.map(body_site_class).values,
                            collection_date=smp.sample_key.map(A.collection_date if "collection_date" in A else pd.Series(dtype=object)).values, subject_id_raw=None))
    att = attrs.rename(columns={"value": "attr_value"})
    conv = pd.DataFrame(columns=["study_accession", "regex"])
    import tempfile
    coh = pd.DataFrame(columns=["cohort_id", "study_accessions", "unique_infants_est"])
    ss = SR.resolve(det, sam, att, conv, coh, outdir=tempfile.mkdtemp())[0]
    # join to the study's existing subjects: same subject_key -> reuse linked_infant_subject_key; new mothers link by family prefix
    ex = subj0.drop_duplicates("subject_key").set_index("subject_key")
    ss["linked_infant_subject_key"] = ss.linked_infant_subject_key.where(ss.linked_infant_subject_key.notna(), ss.subject_key.map(ex.linked_infant_subject_key))
    fam = attrs[attrs.attr_key_norm.isin(SR.FAMILY_KEYS)].drop_duplicates("sample_key").set_index("sample_key").value
    inf = subj0[(subj0.role == "infant") & subj0.subject_key.notna()]
    fam_inf = inf.assign(fam=inf.subject_id_resolved.astype(str).str.split("_").str[0]).groupby("fam").subject_key.agg(lambda x: sorted(set(x))).to_dict()
    def link(r):
        if pd.notna(r.linked_infant_subject_key) or r.role != "mother":
            return r.linked_infant_subject_key
        c = fam_inf.get(str(fam.get(r.sample_key)))
        return "|".join(c) if c and len(c) <= 3 else None
    ss["linked_infant_subject_key"] = ss.apply(link, axis=1)
    # year-granular (adult) ages repeat across a subject's timepoints and cannot order them: when the age basis yields fewer
    # distinct timepoints than the timepoint labels do, re-rank by the label (the study's existing rows use t_basis=timepoint_label)
    tpn = ss.timepoint_label.map(SR.tp_numeric)
    for key, idx in ss[ss.subject_key.notna()].groupby("subject_key").indices.items():
        g = ss.iloc[idx]; labels = tpn.iloc[idx]
        if len(g) > 1 and (g.t_basis == "age_days").all() and labels.notna().sum() >= max(2, int(0.5 * len(g))) and labels.nunique() > g.n_timepoints_subject.max():
            ss.loc[g.index, "t_index"] = labels.rank(method="dense").values
            ss.loc[g.index, "n_timepoints_subject"] = int(labels.dropna().nunique())
            ss.loc[g.index, "t_basis"] = "timepoint_label"
    ss["n_existing_samples_same_subject"] = ss.subject_key.map(subj0.subject_key.value_counts()).fillna(0).astype(int)
    return ss


# ------------------------------------------------------------------------------------------------ 5. sandpiper
def sandpiper_delta(study, new_runs, sample_keys, template_qc, template_summary, release_id, package_version, enabled, purpose="gapfill_sandpiper", rate_s=2.0):
    """Per-run API route. Returns (run_qc_new, sample_summary_new, stats). Without --sandpiper the API is not called
    and every run is 'not_in_snapshot_api_unavailable'."""
    import sandpiper_lib as SL
    stats = dict(enabled=bool(enabled), n_runs=len(new_runs), n_api_calls=0, n_in_sandpiper=0, n_profiles=0, errors=0)
    meta_rows, profiles = {}, []
    if enabled:
        HL, _ = _hl()
        for acc in sorted(new_runs.run_accession):
            r = HL.fetch(SANDPIPER_API + f"metadata/{acc}", purpose=purpose)
            stats["n_api_calls"] += 1
            body = r.get("body") or b""
            body = body.decode("utf-8", "ignore") if isinstance(body, bytes) else str(body)
            found = r.get("status") == 200 and '"error"' not in body[:80]
            meta_rows[acc] = dict(found=found, status=r.get("status"))
            if found:
                try:
                    meta_rows[acc]["meta"] = json.loads(body)
                except json.JSONDecodeError:
                    pass
                stats["n_in_sandpiper"] += 1
                if not r.get("from_cache"):
                    time.sleep(rate_s)
                p = HL.fetch(SANDPIPER_API + f"condensed_csv_with_extras/{acc}?taxonomy_type=gtdb", purpose=purpose)
                stats["n_api_calls"] += 1
                pb = p.get("body") or b""; pb = pb.decode("utf-8", "ignore") if isinstance(pb, bytes) else str(pb)
                if p.get("ok") and pb.count("\n") > 1:
                    pf = pd.read_csv(io.StringIO(pb), sep="\t", dtype={"sample": str})
                    pf["run"] = acc; profiles.append(pf); stats["n_profiles"] += 1
            if not r.get("from_cache"):
                time.sleep(rate_s)
    horizon = pd.Timestamp(SNAPSHOT_HORIZON)
    qc = []
    for r in new_runs.itertuples(index=False):
        m = meta_rows.get(r.run_accession, {})
        fp = pd.to_datetime(r.first_public, errors="coerce")
        if m.get("found"):
            miss = "profiled"
        elif not enabled:
            miss = "not_in_snapshot_api_unavailable"
        elif pd.notna(fp) and fp > horizon:
            miss = "published_after_snapshot_horizon"
        elif str(r.instrument_platform).upper() != "ILLUMINA":
            miss = "non_illumina_platform"
        else:
            miss = "sra_illumina_not_in_snapshot" if str(r.run_accession).startswith("SRR") else ("ena_illumina_not_in_snapshot" if str(r.run_accession).startswith("ERR") else "ddbj_illumina_not_in_snapshot")
        row = {c: None for c in template_qc.columns}
        row.update(run_accession=r.run_accession, study_accession=study, sample_accession=r.sample_accession, catalog_sample_key=r.sample_accession, sample_unit="biosample",
                   in_sandpiper=bool(m.get("found")), sp_miss_reason=miss, library_strategy=r.library_strategy, library_source=r.library_source, instrument_platform=r.instrument_platform,
                   base_count=pd.to_numeric(r.base_count, errors="coerce"), first_public=fp, organism=r.scientific_name, sp_warning_present=False,
                   sp_flag_non_metagenome_strict=False, sp_flag_non_metagenome_loose=False, sp_nonmeta_class="not_flagged", sp_flag_synthetic=False, sp_flag_rna_strict=False, sp_flag_rna_loose=False,
                   sandpiper_url=(SANDPIPER_API.replace("api/", "run/") + r.run_accession) if m.get("found") else None,
                   sandpiper_version="2.0.0", taxonomy_db="GTDB", taxonomy_version="R232", zenodo_record=str(template_qc.zenodo_record.dropna().iloc[0]) if template_qc.zenodo_record.notna().any() else None,
                   release_added=release_id, release_retired=None, package_added=package_version)
        qc.append(row)
    stats["api_note"] = "api_checked_per_run" if enabled else "api_not_called"
    run_qc = pd.DataFrame(qc)
    summary = pd.DataFrame(columns=list(template_summary.columns))
    if profiles:
        raw = pd.concat(profiles, ignore_index=True)
        raw = raw.rename(columns={"coverage": "coverage"})
        raw["sample_key"] = raw.run.map(dict(zip(new_runs.run_accession, new_runs.sample_accession)))
        agg = raw.groupby(["sample_key", "taxonomy"], as_index=False).coverage.sum()       # SUM unfilled coverage across runs (A16/B6)
        filled = SL.fill_profile(agg, key="sample_key", tax="taxonomy", cov="coverage")
        prof = SL.normalise(filled, key="sample_key")
        rows = []
        for sk, g in prof.groupby("sample_key"):
            gen = g[(g.rank_i == 6)]
            def ra(rank_i, taxon):
                x = g[(g.rank_i == rank_i) & (g.taxon == taxon)].rel_abundance
                return float(x.sum()) if len(x) else 0.0
            top = gen[gen.taxon != "unassigned_at_genus"].sort_values("rel_abundance", ascending=False)
            runs_of = sorted(raw[raw.sample_key == sk].run.unique())
            rows.append(dict(sample_key=sk, sp_n_runs_profiled=len(runs_of), sp_root_coverage=float(g.root_coverage.iloc[0]),
                             sp_ra_g_Bifidobacterium=ra(6, "g__Bifidobacterium"), sp_ra_f_Bacteroidaceae=ra(5, "f__Bacteroidaceae"), sp_ra_g_Bacteroides=ra(6, "g__Bacteroides"),
                             sp_ra_g_Phocaeicola=ra(6, "g__Phocaeicola"), sp_ra_enterobacterales_core=sum(ra(6, f"g__{t}") for t in ["Escherichia", "Klebsiella", "Enterobacter", "Citrobacter", "Salmonella", "Serratia"]),
                             sp_ra_g_Escherichia=ra(6, "g__Escherichia"), sp_ra_g_Klebsiella=ra(6, "g__Klebsiella"), sp_ra_f_Lachnospiraceae=ra(5, "f__Lachnospiraceae"),
                             sp_ra_f_Lactobacillaceae=ra(5, "f__Lactobacillaceae"), sp_ra_g_Streptococcus=ra(6, "g__Streptococcus"), sp_ra_g_Staphylococcus=ra(6, "g__Staphylococcus"),
                             sp_ra_g_Enterococcus=ra(6, "g__Enterococcus"), sp_ra_g_Veillonella=ra(6, "g__Veillonella"), sp_ra_g_Clostridioides=ra(6, "g__Clostridioides"),
                             sp_ra_unassigned_genus=ra(6, "unassigned_at_genus"), sp_ra_unassigned_species=ra(7, "unassigned_at_species"),
                             sp_top_genus=(top.taxon.iloc[0] if len(top) else None), sp_top_genus_ra=(float(top.rel_abundance.iloc[0]) if len(top) else np.nan),
                             sp_shannon_genus=SL.shannon(gen.rel_abundance.values), sp_n_genera_ge1pct=int((top.rel_abundance >= 0.01).sum()),
                             sandpiper_url=SANDPIPER_API.replace("api/", "run/") + runs_of[0], sp_runs_profiled=";".join(runs_of), sp_profiled=True,
                             taxonomy_db="GTDB", taxonomy_version="R232", sandpiper_version="2.0.0", zenodo_record=None, sp_nonmeta_class="not_flagged",
                             release_added=release_id, release_retired=None, package_added=package_version))
        summary = pd.DataFrame(rows)
        nt = new_runs.groupby("sample_accession").run_accession.size()
        summary["sp_n_runs_total"] = summary.sample_key.map(nt); summary["sp_partial"] = summary.sp_n_runs_profiled < summary.sp_n_runs_total
        summary["sp_low_depth"] = summary.sp_root_coverage < 2
        summary = summary.reindex(columns=list(template_summary.columns))
    return run_qc, summary, stats


# ------------------------------------------------------------------------------------------------ 6. outputs
def classify_body_site(attrs, new_runs):
    """Deterministic body-site class from isolation_source / sample_type / body_site / organism text (scope_constants vocab)."""
    import scope_constants_v3 as SC3
    A = attrs.pivot_table(index="sample_key", columns="attr_key_norm", values="value", aggfunc="first")
    org = new_runs.drop_duplicates("sample_accession").set_index("sample_accession").scientific_name
    out = {}
    for sk in A.index:
        txt = " ".join(str(A.loc[sk, c]).lower() for c in ("isolation_source", "sample_type", "body_site", "env_medium", "tissue", "host_body_site", "organism") if c in A.columns and isinstance(A.loc[sk, c], str))
        txt = f"{txt} {str(org.get(sk, '')).lower()}"
        words = set(re.findall(r"[a-z]+(?: [a-z]+)?", txt))
        toks = set(re.findall(r"[a-z]+", txt))
        if toks & SC3.BODY_SITE_PRIMARY or words & SC3.BODY_SITE_PRIMARY:
            out[sk] = "primary"
        elif toks & SC3.BODY_SITE_LINKED or words & SC3.BODY_SITE_LINKED:
            out[sk] = "linked"
        elif toks & SC3.BODY_SITE_EXCLUDE or words & SC3.BODY_SITE_EXCLUDE:
            out[sk] = "excluded"
        else:
            out[sk] = "unknown"
    return pd.Series(out)


def derive_scope(w, subj, det, sm0):
    """age_scope / basis / role fallbacks / catalog_scope exactly as the package documents (DATA_DICTIONARY age_scope)."""
    age = pd.to_numeric(w.age_at_collection_days, errors="coerce")
    oos = det[(det.field_name == "age_at_collection_days") & det.parse_note.astype(str).str.startswith("out_of_scope_adult")]
    w["adult_age_flag"] = w.sample_key.isin(set(oos.sample_key))
    inf_ev = det[det.field_name.isin(["age_at_collection_days", "preterm_status", "gestational_age_weeks"]) & (det.scope == "sample")]
    ratio = sm0.get("n_infant_samples_est"); nscope = sm0.get("n_infant_scope_samples")
    scope, basis, role = [], [], []
    other_ev = inf_ev[inf_ev.field_name != "age_at_collection_days"].groupby("sample_key").field_name.first().to_dict()
    for i, r in enumerate(w.itertuples(index=False)):
        a = age.iloc[i]
        rr, rs = r.role, r.role_source
        if r.adult_age_flag:
            s, b = "adult_flagged", "committed age >1100 d"
            if rs not in ("attr_role", "sample_name_token", "body_site_raw", "body_site_class=linked"):
                rr, rs = ("adult" if pd.notna(a) and a >= 18 * 365.25 else "child"), "age_scope:adult_flagged"
        elif rr in ("mother", "other") and rs:
            s, b = "non_infant_role", f"role {rr} from {rs}"
        elif pd.notna(a) and a <= 1100:
            s, b = "infant_evidenced", "age_at_collection_days<=1100"
        elif r.sample_key in other_ev:
            s, b = "infant_evidenced", other_ev[r.sample_key]
        elif pd.notna(ratio) and nscope:
            fr = float(ratio) / float(nscope)
            s, b = ("study_all_infant" if fr >= 0.9 else "age_unknown_mixed_study"), f"n_infant_samples_est/n_infant_scope_samples={fr:.2f}"
        else:
            s, b = "age_unknown_no_study_estimate", "triage gave no n_infant_samples_est"
        if s in ("infant_evidenced", "study_all_infant") and rr in (None, "unknown"):
            rr, rs = "infant", f"age_scope:{s}"
        scope.append(s); basis.append(b); role.append((rr, rs if rs else "none"))
    w["age_scope"] = scope; w["age_scope_basis"] = basis
    w["role"] = [x[0] for x in role]; w["role_source"] = [x[1] for x in role]
    w["catalog_scope"] = w.age_scope.isin(["infant_evidenced", "study_all_infant"]) & w.body_site_class.isin(["primary", "unknown"])
    return w


def build_outputs(study, new_runs, det, subj, attrs, pkg_tables, run_qc, sp_summary, release_id, package_version, out):
    wide0 = pkg_tables["wide"]; smw = pkg_tables["smw"]; runs0 = pkg_tables["runs"]
    w0 = wide0[wide0.study_accession == study]; sm0 = smw[smw.study_accession == study].iloc[0].to_dict()
    bsc = classify_body_site(attrs, new_runs)
    smp = new_runs.drop_duplicates("sample_accession").rename(columns={"sample_accession": "sample_key", "secondary_sample_accession": "secondary_sample"})
    A = attrs.pivot_table(index="sample_key", columns="attr_key_norm", values="value", aggfunc="first")
    smp = smp.assign(body_site_class=smp.sample_key.map(bsc).fillna("unknown"), collection_date=smp.sample_key.map(A.collection_date) if "collection_date" in A else None, is_gold_heldout=False)
    cs = pd.DataFrame([dict(study_accession=study, study_title=w0.study_title.iloc[0], cohort_id=w0.cohort_id.iloc[0], cohort_name=w0.cohort_name.iloc[0], first_public_min=w0.first_public_min.iloc[0])])
    adult = pd.DataFrame(dict(sample_key=det[(det.field_name == "age_at_collection_days") & det.parse_note.astype(str).str.startswith("out_of_scope_adult")].sample_key.unique()))
    runs_new = new_runs.reindex(columns=list(runs0.columns)).copy()
    for c in ("read_count", "base_count"):
        if c in runs_new and str(runs0[c].dtype) != "object":
            pass
    sj = subj.rename(columns={})
    w = BW.build_wide(det, smp, sj, runs_new, cs, None, adult, list(SCX.TARGET_FIELDS_EXT[:12]), SCX.EXTENSION_FIELDS)
    # identity + unit columns
    w["sample_unit"] = "biosample"; w["parent_biosample"] = None; w["biosample_accession"] = w.sample_key; w["run_accession"] = None
    w = w.merge(sj[["sample_key", "role_source"]], on="sample_key", how="left")
    w = derive_scope(w, sj, det, sm0)
    # scope columns per field
    sc = det.pivot_table(index="sample_key", columns="field_name", values="scope", aggfunc="first")
    for f in SCX.TARGET_FIELDS_EXT:
        w[f"{f}__scope"] = w.sample_key.map(sc[f]) if f in sc.columns else None
    w["exclusion_reason_code"] = None
    w["body_site"] = None
    # sandpiper columns
    sp_cols = [c for c in wide0.columns if c.startswith("sp_") or c in ("sandpiper_url", "taxonomy_db", "taxonomy_version", "sandpiper_version")]
    if len(sp_summary):
        w = w.merge(sp_summary[[c for c in sp_summary.columns if c in sp_cols or c == "sample_key"]], on="sample_key", how="left")
    for c in sp_cols:
        if c not in w:
            w[c] = None
    w["sp_profiled"] = w.sp_profiled.fillna(False).astype(bool)
    w["sp_n_runs_total"] = w.sample_key.map(new_runs.groupby("sample_accession").run_accession.size()).astype(int)
    w["sp_n_runs_profiled"] = w.sp_n_runs_profiled.fillna(0).astype(int); w["sp_partial"] = w.sp_partial.fillna(False).astype(bool)
    w["sp_flag_non_metagenome"] = w.sp_flag_non_metagenome.fillna(False).astype(bool); w["sp_nonmeta_class"] = w.sp_nonmeta_class.fillna("not_flagged")
    w["panel_scope"] = w.catalog_scope & w.sp_profiled & ~w.sp_low_depth.fillna(False).astype(bool)
    missing_cols = [c for c in wide0.columns if c not in w.columns]
    for c in missing_cols:
        w[c] = None
    extra = [c for c in w.columns if c not in wide0.columns]
    w = w[list(wide0.columns)]
    # dtype alignment (best effort)
    for c in wide0.columns:
        if str(wide0[c].dtype).startswith(("float", "int", "bool")) and not str(w[c].dtype).startswith(("float", "int", "bool")):
            try:
                w[c] = w[c].astype(wide0[c].dtype)
            except (TypeError, ValueError):
                w[c] = pd.to_numeric(w[c], errors="coerce") if str(wide0[c].dtype).startswith(("float", "int")) else w[c]
    assert list(w.columns) == list(wide0.columns), "wide column set drifted"
    # study delta
    all_w = pd.concat([w0, w], ignore_index=True)
    delta = dict(study_accession=study, n_samples=int(len(all_w)), n_runs=int(len(runs0[runs0.study_accession == study]) + len(runs_new)), n_biosamples=int(all_w.sample_key.nunique()),
                 n_sample_rows=int(len(all_w)), n_infant_scope_samples=int(all_w.body_site_class.isin(["primary", "unknown"]).sum()),
                 n_body_site_excluded=int((all_w.body_site_class == "excluded").sum()), n_catalog_scope=int(all_w.catalog_scope.astype(bool).sum()),
                 n_age_scope_infant=int(all_w.age_scope.isin(["infant_evidenced", "study_all_infant"]).sum()), n_adult_flagged=int((all_w.age_scope == "adult_flagged").sum()),
                 n_non_infant_role=int((all_w.age_scope == "non_infant_role").sum()), n_infant_evidenced=int((all_w.age_scope == "infant_evidenced").sum()),
                 n_study_all_infant=int((all_w.age_scope == "study_all_infant").sum()), n_age_unknown_mixed_study=int((all_w.age_scope == "age_unknown_mixed_study").sum()),
                 n_age_unknown_no_study_estimate=int((all_w.age_scope == "age_unknown_no_study_estimate").sum()), n_mothers=int((all_w.role == "mother").sum()),
                 n_infant_role_samples=int((all_w.role == "infant").sum()), sp_n_samples_profiled=int(all_w.sp_profiled.astype(bool).sum()),
                 sp_frac_samples_profiled=round(float(all_w.sp_profiled.astype(bool).mean()), 4), sp_n_runs_profiled=int(sm0.get("sp_n_runs_profiled") or 0) + int(run_qc.in_sandpiper.sum()))
    delta["sp_frac_runs_profiled"] = round(delta["sp_n_runs_profiled"] / delta["n_runs"], 4)
    for f in SCX.TARGET_FIELDS_EXT:
        delta[f"cov_{f}"] = round(float(all_w[f].notna().mean()), 6)
    delta["before"] = {k: (None if (isinstance(sm0.get(k), float) and np.isnan(sm0.get(k))) else (sm0.get(k).item() if hasattr(sm0.get(k), "item") else sm0.get(k))) for k in delta if k in sm0 and k != "study_accession"}
    return w, runs_new, delta, extra


def write_report(study, out, stats, cmp, meta, gate, sp_stats, delta, det, sentinels, w, subj, release_id, package_version):
    L = [f"# GAPFILL_{study}_REPORT — new samples in an included study (release {release_id}, package {package_version})", ""]
    L += ["## 1. Harvest", f"* BioSamples: {stats['n_samples']} new; found {stats['n_found']} (ENA XML {stats['n_ena']}, NCBI efetch fallback {stats['n_ncbi']}, missing {stats['n_missing']}); {stats['n_attr_rows']} attribute rows; {stats['n_experiments']} experiment records.",
          "* Attribute keys (n samples): " + ", ".join(f"`{k}` {v}" for k, v in sorted(cmp["new_attribute_keys"].items())), ""]
    if "keys_only_in_new" in cmp:
        L += ["## 2. Comparison with the study's existing samples", f"* keys only in the new samples: {', '.join(cmp['keys_only_in_new']) or '—'}", f"* keys only in the existing samples: {', '.join(cmp['keys_only_in_existing']) or '—'}"]
        for k, v in cmp.get("value_shift", {}).items():
            L.append(f"* `{k}`: existing {v['existing']} → new {v['new']}")
        L.append("")
    L += ["* existing wide-table classes: " + json.dumps(cmp["existing_wide"]), f"* existing group-scope (R3/R4 cohort_default) rows: {cmp['existing_group_rows_cohort_default']}", ""]
    L += ["## 3. Extraction", f"* committed determinations: {meta['n_committed']} — " + ", ".join(f"{k} {v}" for k, v in sorted(meta['fields_committed'].items())),
          f"* superseded (lower-precedence duplicates within R1): {meta['n_superseded']}; rejected (no value / validator): {meta['n_rejected']}; sentinels (sample × field without evidence): {meta['n_sentinels']}",
          f"* ages committed under the v1.2 `out_of_scope_adult` convention (> 1,100 d; evidence for adult_age_flag): {meta['n_out_of_scope_adult']}",
          f"* validator pass rate on committed rows: {meta['validator_pass_rate']:.1%} (every committed row passed validate_row; out-of-range ages pass every check except the in-scope range, by convention)",
          f"* unit resolution: U1/U2 rules {json.dumps(meta['unit_rules'])[:600]}; U3 adopted: {[r for r in meta['u3_rules'] if r.get('adopted')]}",
          f"* composite subject ids: {meta['composite_subject']}", f"* group rows extended from existing cohort_default statements: {meta['n_group_rows_extended']}", ""]
    if len(gate):
        L += ["### R2 supplementary-table gate", gate.drop(columns=[c for c in ("note",) if c in gate]).to_markdown(index=False), f"* R2 rows committed: {meta.get('n_r2', 0)} ({'no R2 source' if not meta.get('n_r2') else 'header-named columns'})", ""]
    else:
        L += ["### R2", "* no linked own-data paper with a supplementary zip → 'no R2 source'", ""]
    L += ["## 4. Subjects", f"* subjects resolved: {int(subj.subject_key.notna().sum())}/{len(subj)}; subject_keys already present in the study: {int((subj.n_existing_samples_same_subject > 0).sum())}; roles: {subj.role.value_counts().to_dict()}; role_source: {subj.role_source.value_counts(dropna=False).to_dict()}",
          f"* mothers linked to an infant subject: {int(subj[subj.role == 'mother'].linked_infant_subject_key.notna().sum())}/{int((subj.role == 'mother').sum())}; t_basis: {subj.t_basis.value_counts(dropna=False).to_dict()}", ""]
    L += ["## 5. Sandpiper (per-run API delta)", f"* {json.dumps(sp_stats)}", ""]
    L += ["## 6. Wide table", f"* rows {len(w)}; body_site_class {w.body_site_class.value_counts().to_dict()}; age_scope {w.age_scope.value_counts().to_dict()}; role {w.role.value_counts().to_dict()}; catalog_scope {w.catalog_scope.astype(bool).sum()}; adult_age_flag {int(w.adult_age_flag.sum())}",
          f"* n_fields_with_value: {w.n_fields_with_value.value_counts().sort_index().to_dict()}", ""]
    L += ["## 7. Study-level delta (before → after)", "| metric | before | after |", "|---|---|---|"]
    for k, v in delta.items():
        if k in ("study_accession", "before"):
            continue
        L.append(f"| {k} | {delta['before'].get(k, '')} | {v} |")
    L += ["", "## 8. Deviations", *[f"* {d}" for d in meta.get("deviations", [])], ""]
    with open(os.path.join(out, f"GAPFILL_{study}_REPORT.md"), "w") as fh:
        fh.write("\n".join(L))


# ------------------------------------------------------------------------------------------------ main
def run(study, new_runs_path, pkg, out, release_id, package_version, field_map, sandpiper=False, harvest_existing_flag=False, cache_dir=None, deviations=()):
    if cache_dir:
        os.environ.setdefault("CATALOG_CACHE_DIR", cache_dir)
    os.makedirs(out, exist_ok=True)
    new_runs = pd.read_parquet(new_runs_path)
    new_runs = new_runs[new_runs.study_accession == study].copy()
    assert len(new_runs), "no runs for the study in --new-runs"
    fm = pd.read_csv(field_map)
    global FM_KEYS
    FM_KEYS = list(fm[~fm.parser.isin(["haiku", "SKIP"])].attr_key_norm)
    T = dict(runs=pd.read_parquet(os.path.join(pkg, "runs.parquet")), wide=pd.read_parquet(os.path.join(pkg, "sample_metadata_wide.parquet")),
             det=pd.read_parquet(os.path.join(pkg, "sample_determinations.parquet")), subj=pd.read_parquet(os.path.join(pkg, "sample_subjects.parquet")),
             smw=pd.read_parquet(os.path.join(pkg, "study_metadata_wide.parquet")), spq=pd.read_parquet(os.path.join(pkg, "sandpiper_run_qc.parquet")),
             sps=pd.read_parquet(os.path.join(pkg, "sandpiper_sample_summary.parquet")))
    assert study in set(T["smw"].study_accession), f"{study} is not an included study of the package"
    assert not set(new_runs.run_accession) & set(T["runs"].run_accession), "some --new-runs are already in the package"
    assert not set(new_runs.sample_accession) & set(T["wide"].sample_key), "some new BioSamples are already in the package"
    w0 = T["wide"][T["wide"].study_accession == study]; s0 = T["subj"][T["subj"].study_accession == study]
    # 1
    attrs, exps, study_meta, stats = harvest(study, new_runs); log(f"harvest {stats}")
    attrs.to_parquet(os.path.join(out, "sample_attributes_new.parquet"), index=False); exps.to_parquet(os.path.join(out, "experiments_new.parquet"), index=False)
    json.dump(study_meta, open(os.path.join(out, "study_record.json"), "w"), indent=1)
    # 2
    ex_attrs = harvest_existing(w0.sample_key) if harvest_existing_flag else None
    if ex_attrs is not None:
        ex_attrs.to_parquet(os.path.join(out, "sample_attributes_existing.parquet"), index=False)
    cmp = compare_with_existing(study, T["det"], w0, s0, attrs, ex_attrs); json.dump(cmp, open(os.path.join(out, "attribute_comparison.json"), "w"), indent=1, default=str)
    # R2 gate first (its sheets feed U3)
    gate, sheets = r2_gate(study, pkg, new_runs); gate.to_csv(os.path.join(out, "r2_gate.csv"), index=False); log(f"r2 gate sheets={len(gate)} usable={int(gate.r2_usable.sum()) if len(gate) else 0}")
    # 3
    det, superseded, rejected, sentinels, meta = r1_extract(study, new_runs, attrs, fm, T["det"], s0, sheets, release_id, package_version)
    r2 = r2_extract(study, gate, sheets, new_runs, fm, release_id, package_version)
    if len(r2):  # R1 > R2 precedence
        have = set(zip(det.sample_key, det.field_name)); r2 = r2[[(a, b) not in have for a, b in zip(r2.sample_key, r2.field_name)]]
        r2, r2_rej, _ = validate_all(r2); det = pd.concat([det, r2], ignore_index=True)
        sentinels = sentinels[~sentinels.set_index(["record_id", "slot"]).index.isin(set(zip(r2.sample_key, r2.field_name)))]
    meta["n_r2"] = int(len(r2)); meta["validator_pass_rate"] = 1.0 if len(det) else float("nan")
    det.to_parquet(os.path.join(out, "sample_determinations_new.parquet"), index=False)
    superseded.to_parquet(os.path.join(out, "sample_determinations_superseded_new.parquet"), index=False)
    rejected.to_parquet(os.path.join(out, "sample_determinations_rejected_new.parquet"), index=False)
    sentinels.to_parquet(os.path.join(out, "sample_determinations_sentinels_new.parquet"), index=False)
    log(f"determinations committed={len(det)} superseded={len(superseded)} rejected={len(rejected)} sentinels={len(sentinels)} oos_adult={meta['n_out_of_scope_adult']}")
    # 4
    bsc = classify_body_site(attrs, new_runs)
    subj = build_subjects(study, det, new_runs, attrs, s0, bsc)
    # 5
    run_qc, sp_summary, sp_stats = sandpiper_delta(study, new_runs, list(subj.sample_key), T["spq"], T["sps"], release_id, package_version, sandpiper)
    run_qc.to_parquet(os.path.join(out, "sandpiper_run_qc_new.parquet"), index=False); sp_summary.to_parquet(os.path.join(out, "sandpiper_sample_summary_new.parquet"), index=False)
    log(f"sandpiper {sp_stats}")
    # 6
    w, runs_new, delta, extra = build_outputs(study, new_runs, det, subj, attrs, T, run_qc, sp_summary, release_id, package_version, out)
    # subjects table in package shape
    sj = subj.merge(w[["sample_key", "sample_unit", "parent_biosample", "age_scope"]], on="sample_key", how="left")
    sj = sj.reindex(columns=list(T["subj"].columns))
    sj.to_parquet(os.path.join(out, "sample_subjects_new.parquet"), index=False)
    runs_new.to_parquet(os.path.join(out, "runs_new.parquet"), index=False)
    w.to_parquet(os.path.join(out, "samples_new_wide.parquet"), index=False)
    json.dump(delta, open(os.path.join(out, "study_metadata_wide_delta.json"), "w"), indent=1, default=str)
    meta["deviations"] = list(deviations) + ([f"wide columns computed but not in the package schema were dropped: {extra}"] if extra else [])
    if not sandpiper:
        meta["deviations"].append("Sandpiper per-run API not called (--sandpiper off): every run marked not_in_snapshot_api_unavailable")
    if stats["n_ncbi"]:
        meta["deviations"].append(f"{stats['n_ncbi']} BioSamples came from NCBI efetch because ENA returned no record")
    write_report(study, out, stats, cmp, meta, gate, sp_stats, delta, det, sentinels, w, subj, release_id, package_version)
    json.dump(dict(stats=stats, meta={k: v for k, v in meta.items() if k not in ("unit_rules", "u3_rules")}, sandpiper=sp_stats, delta=delta), open(os.path.join(out, "gapfill_summary.json"), "w"), indent=1, default=str)
    log("done")
    return dict(det=det, wide=w, subjects=sj, runs=runs_new, run_qc=run_qc, sp_summary=sp_summary, delta=delta, meta=meta, sentinels=sentinels, gate=gate)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--study", required=True); ap.add_argument("--new-runs", required=True); ap.add_argument("--package", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--release-id", required=True); ap.add_argument("--package-version", required=True)
    ap.add_argument("--field-map", default=os.path.join(_here, "..", "..", "..", "config", "attribute_field_map.csv"))
    ap.add_argument("--cache-dir", default=None); ap.add_argument("--sandpiper", action="store_true"); ap.add_argument("--harvest-existing", action="store_true")
    a = ap.parse_args(argv)
    run(a.study, a.new_runs, a.package, a.out, a.release_id, a.package_version, a.field_map, sandpiper=a.sandpiper, harvest_existing_flag=a.harvest_existing, cache_dir=a.cache_dir)


if __name__ == "__main__":
    main()

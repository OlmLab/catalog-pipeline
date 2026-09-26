"""Steps 2-3 of the sample-unit fix. Needs in namespace: sam, runs, det, per_run, cls_out, tm, tab (attrs of multi BioSamples), LBC, A_studies."""
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
import re, pandas as pd, numpy as np

CONST_SUBJECT = {"sex", "gestational_age_weeks", "preterm_status", "delivery_mode", "birth_weight_grams", "maternal_antibiotics",
                 "subject_id", "multiple_birth", "sibling_in_study"}
CONST_DEPOSIT = {"country", "geo_subregion"}
PER_STOOL = {"age_at_collection_days", "timepoint_label", "feeding_mode", "antibiotic_exposure", "antibiotic_current", "nec_status",
             "probiotic_exposure", "hmo_supplementation", "health_condition"}
STAGE = dict(src_track="sample_unit_fix", decision_stage="auditor_review")
MODEL = "deterministic"

def q12(s):
    return " ".join(str(s).split()[:12])

def vrow(record_id, slot, value, unit, conf, source, quote, outcome="resolved_from_raw"):
    row = {"record_id": record_id, "slot": slot, "value": value, "value_unit": unit, "outcome": outcome, "confidence": float(conf),
           "evidence": [{"source": source, "quote": q12(quote)}], "model": MODEL}
    return LBC.V["validate_row"](row)

def build_samples_v2(sam, runs, a_bs):
    """a_bs: dict biosample -> study for final-class-A BioSamples."""
    s = sam.copy()
    s["sample_unit"] = "biosample"; s["parent_biosample"] = None
    s.loc[s.sample_key.isin(a_bs), "sample_unit"] = "biosample_pooled"
    rn = runs[runs.study_accession.isin(set(a_bs.values()))].copy()
    skset = set(sam.sample_key); sec2key = dict(zip(sam.secondary_sample, sam.sample_key))
    rn["parent"] = [a if a in skset else sec2key.get(b) for a, b in zip(rn.sample_accession, rn.secondary_sample_accession)]
    rn = rn[rn.parent.isin(a_bs)].drop_duplicates("run_accession")
    par = sam.set_index("sample_key")
    child = []
    for r in rn.itertuples(index=False):
        p = par.loc[r.parent]
        child.append(dict(sample_key=r.run_accession, secondary_sample=None, study_accession=r.study_accession,
                          sample_title=r.sample_title if isinstance(r.sample_title, str) else p.sample_title, tax_id=p.tax_id, scientific_name=p.scientific_name,
                          host_tax_id=p.host_tax_id, host_scientific=p.host_scientific, collection_date=p.collection_date, country=p.country,
                          subject_id_raw=p.subject_id_raw, body_site_raw=p.body_site_raw, body_site_class=p.body_site_class, body_site_class_source=p.body_site_class_source,
                          library_name=r.library_name, first_public=r.first_public if isinstance(r.first_public, str) else p.first_public, n_runs=1, n_studies=p.n_studies,
                          is_gold_heldout=p.is_gold_heldout, subject_id_source=p.subject_id_source, sample_unit="run", parent_biosample=r.parent))
    child = pd.DataFrame(child)
    out = pd.concat([s, child[s.columns]], ignore_index=True)
    return out, child

def select_per_run(pr, tm):
    """one value per (run, field): own_data > reused, non-pooled > pooled, then table coverage, then confidence."""
    d = pr.copy()
    st = dict(zip(zip(tm.pmcid, tm.file, tm.sheet.fillna("").astype(str), tm.study_accession), zip(tm.relation, tm.status)))
    key = list(zip(d.pmcid, d.tab.str.split("/").str[1], d.tab.str.split("/").str[2], d.study_accession))
    d["relation"] = [st.get(k, (None, None))[0] for k in key]
    d["pooled"] = [st.get(k, (None, ""))[1] == "mapped_pooled" for k in key]
    d["_rank"] = [(0 if r == "own_data" else 2) + (1 if p else 0) for r, p in zip(d.relation, d.pooled)]
    cov = d.groupby(["study_accession", "field_name", "tab"]).run_accession.nunique().rename("_cov").reset_index()
    d = d.merge(cov, on=["study_accession", "field_name", "tab"])
    nv = d.groupby(["run_accession", "field_name"]).value_normalized.nunique().rename("n_values_in_route").reset_index()
    d = d.sort_values(["run_accession", "field_name", "_rank", "_cov", "confidence"], ascending=[True, True, True, False, False])
    best = d.drop_duplicates(["run_accession", "field_name"]).merge(nv, on=["run_accession", "field_name"], how="left")
    return best

def build_determinations(det, per_run, child, cls_out, tm, attrs_multi):
    a_rows = cls_out[cls_out.final_class == "A"]
    single = {b: bool(re.search(r"from infant \d+", str(q))) for b, q in zip(a_rows.biosample, a_rows.c1_quote)}
    # static conflicts within a BioSample's runs mark it multi-subject
    ms = per_run[per_run.field_name.isin(CONST_SUBJECT)].groupby(["sample_key", "field_name"]).value_normalized.nunique()
    multi_subject = set(ms[ms > 1].index.get_level_values(0))
    for b in multi_subject: single[b] = False
    child_parent = dict(zip(child.sample_key, child.parent_biosample))
    new, rej, sup = [], [], []
    # ---- (a) per-run R2 values
    best = select_per_run(per_run[per_run.run_accession.isin(child_parent) & (per_run.field_name != "collection_date")], tm)
    for r in best.itertuples(index=False):
        unit = "days" if r.field_name == "age_at_collection_days" else ("weeks" if r.field_name == "gestational_age_weeks" else None)
        conf = min(float(r.confidence), 0.75)
        ok, msg = vrow(r.run_accession, r.field_name, r.value_normalized, unit, conf, "paper.supp.table", r.evidence_quote)
        row = dict(sample_key=r.run_accession, field_name=r.field_name, study_accession=r.study_accession, field_value=r.field_value, value_normalized=r.value_normalized,
                   confidence=conf, evidence_source="paper.supp.table", evidence_locator=r.evidence_locator, evidence_quote=q12(r.evidence_quote), evidence_limited_to_abstract=0,
                   determined_by=r.determined_by, route="R2", scope="sample", parse_note=r.parse_note + ("; pooled" if r.pooled else ""), group_audit=None,
                   parent_biosample=child_parent[r.run_accession], n_values_in_route=r.n_values_in_route, **STAGE)
        (new if ok else rej).append(row if ok else {**row, "reject_reason": msg})
    # ---- (b) R1 propagation from parent (per-infant constants; deposit constants always, subject constants only for single-subject records)
    geo = attrs_multi[attrs_multi.attr_key_norm == "geo_loc_name"].groupby("sample_key").attr_value.first().to_dict()
    for r in det[det.sample_key.isin(set(child_parent.values())) & (det.route == "R1")].itertuples(index=False):
        f = r.field_name
        if f in PER_STOOL:
            continue
        if f in CONST_SUBJECT and not single.get(r.sample_key, False):
            rej.append(dict(sample_key=r.sample_key, field_name=f, study_accession=r.study_accession, value_normalized=r.value_normalized, route="R1",
                            reject_reason="subject-scope constant not propagated: parent BioSample is multi-subject or subject multiplicity unknown", **STAGE))
            continue
        src = r.evidence_source
        if src == "biosample_attr" and str(r.evidence_quote).strip() == str(geo.get(r.sample_key, "")).strip():
            src = "sample.attr.geo_loc_name"
        for run in child[child.parent_biosample == r.sample_key].sample_key:
            unit = "weeks" if f == "gestational_age_weeks" else None
            ok, msg = vrow(run, f, r.value_normalized, unit, r.confidence, src, r.evidence_quote)
            row = dict(sample_key=run, field_name=f, study_accession=r.study_accession, field_value=r.field_value, value_normalized=r.value_normalized, confidence=r.confidence,
                       evidence_source=src, evidence_locator=r.evidence_locator, evidence_quote=q12(r.evidence_quote), evidence_limited_to_abstract=r.evidence_limited_to_abstract,
                       determined_by=str(r.determined_by) + "+propagated_from_parent", route="R1", scope="biosample", parse_note=f"propagated from parent {r.sample_key}; " + str(r.parse_note or ""),
                       group_audit=r.group_audit, parent_biosample=r.sample_key, n_values_in_route=1, **STAGE)
            (new if ok else rej).append(row if ok else {**row, "reject_reason": msg})
    # ---- superseded parent rows: R2 rows from run-keyed tables (per-stool fields; all fields for multi-subject parents)
    rk = det.parse_note.str.contains(r"map=(?:orig:)?(?:affix_)?\w+:(?:run|library)", regex=True, na=False)
    par_r2 = det[det.sample_key.isin(set(child_parent.values())) & (det.route == "R2") & rk]
    for r in par_r2.itertuples(index=False):
        if r.field_name in PER_STOOL or not single.get(r.sample_key, False):
            d = r._asdict(); d["superseded_by"] = "run-level"
            d["superseded_reason"] = "per-stool value collapsed from run-keyed table" if r.field_name in PER_STOOL else "static value collapsed from multi-subject BioSample"
            sup.append(d)
    return pd.DataFrame(new), pd.DataFrame(rej), pd.DataFrame(sup), single

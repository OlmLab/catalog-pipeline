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

import pandas as pd, numpy as np, json
def build_wide(det, smp, subj, runs, cs, coh, adult, fields, ext_fields=()):
    F = list(fields) + list(ext_fields) + ["sex","timepoint_label","subject_id"]
    d = det[det.field_name.isin(F)].copy()
    val = d.pivot_table(index="sample_key", columns="field_name", values="value_normalized", aggfunc="first").reindex(columns=F)
    conf = d.pivot_table(index="sample_key", columns="field_name", values="confidence", aggfunc="first").reindex(columns=F).add_suffix("__confidence")
    rt = d.pivot_table(index="sample_key", columns="field_name", values="route", aggfunc="first").reindex(columns=F).add_suffix("__route")
    w = smp[["sample_key","study_accession","secondary_sample","sample_title","body_site_class","collection_date","is_gold_heldout"]].set_index("sample_key")
    w = w.join(val).join(conf).join(rt)
    sj = subj.set_index("sample_key")[["subject_key","role","t_index","n_timepoints_subject","linked_infant_subject_key"]]
    w = w.join(sj, how="left")
    r = runs.groupby("sample_accession").agg(run_accessions=("run_accession", lambda s: ";".join(sorted(s))), n_runs=("run_accession","size"), instrument_model=("instrument_model", lambda s: ";".join(sorted(set(s.dropna().astype(str)))[:3])), library_layout=("library_layout","first"), read_count_total=("read_count", lambda s: pd.to_numeric(s, errors="coerce").sum()))
    w = w.join(r, how="left")
    st = cs.set_index("study_accession")[["study_title","cohort_id","cohort_name","first_public_min"]]
    w = w.join(st, on="study_accession")
    w["adult_age_flag"] = w.index.isin(set(adult.sample_key))
    for c in F:
        if c.endswith(("_days","_weeks","_grams")): w[c] = pd.to_numeric(w[c], errors="coerce")
    w["n_fields_with_value"] = val.notna().sum(axis=1).reindex(w.index).fillna(0).astype(int)
    w["ena_sample_url"] = "https://www.ebi.ac.uk/ena/browser/view/" + w.index.astype(str)
    w["ena_study_url"] = "https://www.ebi.ac.uk/ena/browser/view/" + w.study_accession.astype(str)
    return w.reset_index()

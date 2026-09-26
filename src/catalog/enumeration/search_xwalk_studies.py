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

import sys, os, io, json, time, re
# (sys.path handled by the repo layout shim above)
import pandas as pd
import harvest_lib as HL
names = pd.read_csv("cohort_name_list.csv")
names = names[names.searchable]
toks = sorted({t for j in names.search_tokens for t in json.loads(j) if len(t)>=3})
print("tokens", len(toks), flush=True)
FIELDS = ["study_accession","secondary_study_accession","study_title","description","tax_id","scientific_name","center_name","first_public"]
out = []; log = []
for i,t in enumerate(toks):
    t2 = t.replace('"','')
    q = f'study_title="*{t2}*" OR description="*{t2}*"'
    tsv = HL.ena_search("study", q, FIELDS, limit=5000, purpose="cohort_xwalk_study_search")
    n = 0
    if tsv and tsv.strip():
        df = pd.read_csv(io.StringIO(tsv), sep="\t", dtype=str, on_bad_lines="skip", keep_default_na=False)
        n = len(df); df["token"] = t; out.append(df)
    log.append({"token": t, "n_hits": n, "saturated": n>=5000})
    if i % 50 == 0: print(i, t, n, flush=True)
tsv = HL.ena_search("study", 'study_title="*NCT0*" OR description="*NCT0*"', FIELDS, limit=0, purpose="cohort_xwalk_study_search_nct")
df = pd.read_csv(io.StringIO(tsv), sep="\t", dtype=str, on_bad_lines="skip", keep_default_na=False) if tsv and tsv.strip() else pd.DataFrame(columns=FIELDS)
df["token"] = "__NCT__"; out.append(df); print("NCT studies", len(df), flush=True)
res = pd.concat(out, ignore_index=True)
res.to_parquet("xwalk_study_search_raw.parquet", index=False)
pd.DataFrame(log).to_csv("xwalk_study_search_log.csv", index=False)
print("done", len(res), flush=True)

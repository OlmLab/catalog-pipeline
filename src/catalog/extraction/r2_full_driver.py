"""Driver for the R2 full re-run (v2 gate). Expects in namespace: wl, samples, runs, attrs, existing_r12, host, HL, R2, LBC.
Processes studies smallest-first in chunks; per chunk: gate -> new-accepted tables -> Haiku classify -> extract -> filter -> checkpoint."""
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
import os, json, time, sys
import pandas as pd, numpy as np

OUT = "r2_full_v2"
LOG = open(f"{OUT}_progress.log", "a")

def log(msg):
    LOG.write(time.strftime("%H:%M:%S ") + msg + "\n"); LOG.flush()

# ---- validator wrapper capturing rejected rows
REJECTED = []
_orig_validate = LBC.V["validate_row"]
def _validate_capture(row, sources_text=None):
    ok, msg = _orig_validate(row, sources_text)
    if not ok:
        REJECTED.append(dict(sample_key=row.get("record_id"), field_name=row.get("slot"), value_normalized=row.get("value"),
                             confidence=row.get("confidence"), evidence_quote=(row.get("evidence") or [{}])[0].get("quote"), reject_reason=msg))
    return ok, msg
LBC.V["validate_row"] = _validate_capture

SYSTEM = open(_prompt_path("r2_column_classify_system.txt")).read()

def process_chunk(chunk_studies, per_table_budget=120):
    t0 = time.time()
    mapdf, tables_ok = R2.gate(chunk_studies, wl, samples, runs, HL, attrs=attrs, per_table_budget=per_table_budget)
    if len(mapdf):
        mapdf["tab_key"] = mapdf.pmcid + "/" + mapdf.file + "/" + mapdf.sheet.astype(str)
        mapdf["previously_accepted"] = mapdf.tab_key.isin(acc_loc)
    # new tables only -> classification/extraction
    new_tabs = [tb for tb in tables_ok if (tb["pmcid"] + "/" + tb["file"] + "/" + str(tb["sheet"])) not in acc_loc]
    for i, tb in enumerate(new_tabs):
        tb["table_id"] = f"T{i}"
    stats = {"requests": 0, "tokens": 0}
    det, det_all = pd.DataFrame(), pd.DataFrame()
    if new_tabs:
        res = R2.run(chunk_studies, wl, samples, runs, HL, host, out_prefix=f"{OUT}_chunk", system_text=SYSTEM, batch=15, max_concurrency=6,
                     gated=(mapdf, new_tabs), attrs=attrs)
        det, _, stats = res[0], res[1], res[2]
        det_all = res[3] if len(res) > 3 else det
    log(f"chunk {chunk_studies[0]}..{chunk_studies[-1]} n={len(chunk_studies)} tables={len(mapdf)} accepted={len(tables_ok)} new={len(new_tabs)} det={len(det)} tok={stats.get('tokens',0)} {time.time()-t0:.0f}s")
    return mapdf, det, det_all, stats, len(new_tabs)

def filter_new(det):
    if not len(det):
        return det, 0
    keep = [(sk, f) not in existing_r12 for sk, f in zip(det.sample_key, det.field_name)]
    return det[np.array(keep)], int(len(det) - sum(keep))

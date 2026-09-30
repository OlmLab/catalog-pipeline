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

import sys, os, time, json, urllib.parse, pandas as pd
# (sys.path handled by the repo layout shim above)
import harvest_lib as HL
seeds = pd.read_csv("snowball_seeds.csv")
out = []; log = []
last = 0.0
for i, r in seeds.iterrows():
    for direction in ("references", "citations"):
        attempts = 0
        while True:
            wait = 1.05 - (time.time() - last)
            if wait > 0: time.sleep(wait)
            url = (f"https://api.semanticscholar.org/graph/v1/paper/{r.s2_id}/{direction}?limit=1000&fields=" + urllib.parse.quote("externalIds,title,year,venue,abstract,isOpenAccess"))
            res = HL.fetch(url, purpose="snowball_s2")
            last = time.time()
            st = res.get("status")
            if st == 429 and attempts < 5:
                attempts += 1; time.sleep(5 * attempts); continue
            break
        body = None
        if res.get("ok"):
            try: body = json.loads(res["body"])
            except Exception: body = None
        n = 0
        if isinstance(body, dict):
            data = body.get("data") or []
            n = len(data)
            for d in data:
                p = d.get("citedPaper") if direction == "references" else d.get("citingPaper")
                if p: out.append({"seed_paper_id": r.paper_id, "seed_s2_id": r.s2_id, "direction": direction, **{k: p.get(k) for k in ("paperId","title","year","venue","abstract","isOpenAccess")}, "externalIds": json.dumps(p.get("externalIds") or {}), "next": body.get("next")})
        log.append({"seed_paper_id": r.paper_id, "s2_id": r.s2_id, "direction": direction, "status": st, "ok": res.get("ok"), "n": n, "from_cache": res.get("from_cache"), "attempts": attempts})
    if i % 25 == 0:
        print(i, len(out), flush=True)
        pd.DataFrame(out).to_parquet("s2_raw_partial.parquet"); pd.DataFrame(log).to_csv("s2_log.csv", index=False)
pd.DataFrame(out).to_parquet("s2_raw.parquet"); pd.DataFrame(log).to_csv("s2_log.csv", index=False)
print("DONE", len(out))

"""Disk janitor: supplementary ZIP blobs > KEEP_MB are mined (if <= 200 MB) then replaced by a stub.
Runs until fetch_progress.log contains DONE, then one final pass."""
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
import os, sys, time, json, sqlite3
# (sys.path handled by the repo layout shim above)
import pandas as pd
import mine_accessions2 as MA

KEEP = 20 * 1024 * 1024
MAXZ = 200 * 1024 * 1024
os.makedirs("mined", exist_ok=True)
log = open("janitor_log.jsonl", "a")

def pass_once():
    con = sqlite3.connect("harvest_cache/http_cache.sqlite", timeout=60)
    rows = con.execute("SELECT url, blob_sha, bytes FROM http_cache WHERE url LIKE '%supplementaryFiles' AND bytes > ? AND blob_sha IS NOT NULL", (KEEP,)).fetchall()
    con.close()
    mentions, done = [], []
    for url, sha, nb in rows:
        p = MA.BLOB_DIR / sha[:2] / sha
        if not p.exists() or p.stat().st_size < 1024:
            continue
        pm = url.split("/")[-2]
        status = "stubbed_gt200mb_not_mined"
        if nb <= MAXZ:
            try:
                ms, lg = MA.mine_zip(p.read_bytes(), pm, pm)
                mentions.extend(ms); status = f"mined_not_retained:{len(ms)}"
            except Exception as e:
                status = f"mine_error:{type(e).__name__}"
        p.write_bytes(json.dumps({"stub": "not_retained", "bytes": nb, "status": status}).encode())
        done.append(pm)
        log.write(json.dumps({"pmcid": pm, "bytes": nb, "status": status}) + "\n"); log.flush()
    if mentions:
        pd.DataFrame(mentions).to_parquet(f"mined/mentions_zip_janitor_{time.strftime('%H%M%S')}.parquet", index=False)
    if done:
        with open("mined/done_zip.txt", "a") as f:
            f.write("\n".join(done) + "\n")
    return len(done), len(mentions)

while True:
    n, m = pass_once()
    if n:
        print(time.strftime("%H:%M:%S"), "stubbed", n, "mentions", m, flush=True)
    if os.path.exists("fetch_progress.log") and "DONE" in open("fetch_progress.log").read():
        pass_once(); print("janitor finished", flush=True); break
    time.sleep(60)

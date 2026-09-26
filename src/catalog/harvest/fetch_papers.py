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

import sys, os, json, time
# (sys.path handled by the repo layout shim above)
import harvest_lib as HL
L = json.load(open('handoff/fetch_lists.json'))
MAXZ = 200*1024*1024
log = open('fetch_log.jsonl','a')
def run(ids, kind, fn):
    ok=err=skip=cached=0; t0=time.time()
    for i in range(0, len(ids), 40):
        chunk = ids[i:i+40]
        urls = {(f"{HL.EPMC}/{p}/fullTextXML" if kind=='xml' else f"{HL.EPMC}/{p}/supplementaryFiles"): p for p in chunk}
        res = HL.fetch_many(list(urls), purpose=('epmc_fulltext' if kind=='xml' else 'epmc_suppl'), workers=4, max_retries=2, timeout=60)
        for u, r in res.items():
            n = len(r.get('body') or b'')
            st = 'ok' if r.get('ok') else 'err'
            if kind=='zip' and n > MAXZ: st='skipped_gt200mb'
            if r.get('from_cache'): cached+=1
            ok += st=='ok'; err += st=='err'; skip += st.startswith('skipped')
            log.write(json.dumps({'kind':kind,'pmcid':urls[u],'status':st,'http':r.get('status'),'bytes':n,'from_cache':r.get('from_cache'),'error':r.get('error')})+'\n')
        log.flush()
        done=i+len(chunk)
        if done % 480 < 40 or done==len(ids):
            print(f"{kind} {done}/{len(ids)} ok={ok} err={err} skip={skip} cached={cached} {time.time()-t0:.0f}s", flush=True)
    return ok,err,skip
print(run(L['A'],'xml',None)); print(run(L['S'],'zip',None)); print('DONE', flush=True)

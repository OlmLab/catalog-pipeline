"""Build OUTPUT-CONVENTION study rows + companion run records for candidate INSDC studies."""
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
import io, json, re
import pandas as pd
import harvest_lib as HL
import scope_constants as SC

INFANT_RE = re.compile(r"infant|neonat|newborn|preterm|premature|baby|babies|toddler|meconium|NICU|early.life|mother.{0,10}infant", re.I)
RUN_FIELDS = list(SC.ENA_RUN_FIELDS)


def fetch_post(url, payload, purpose="post", timeout=180, max_retries=4):
    """Cached, rate-limited, logged JSON POST built on harvest_lib's limiter/cache/log.
    Cache key = url + '#POST#' + canonical JSON body (stored in http_cache.url)."""
    import time, urllib.parse
    body_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    key = url + "#POST#" + body_json
    host = urllib.parse.urlparse(url).netloc
    uh = HL._uhash(key)
    cc = HL._cache_conn()
    row = cc.execute("SELECT status, blob_sha, bytes, error FROM http_cache WHERE url_hash=?", (uh,)).fetchone()
    if row and row[1]:
        blob = HL.BLOB_DIR / row[1][:2] / row[1]
        if blob.exists():
            HL._log_call(key, host, row[0], row[2], row[1], True, purpose)
            return {"ok": str(row[0]) == "200", "status": row[0], "body": blob.read_bytes(), "from_cache": True, "url": key, "error": row[3]}
    headers = {"User-Agent": HL.USER_AGENT, "Accept": "application/json, */*", "Content-Type": "application/json"}
    last_err = None
    for attempt in range(max_retries):
        HL.LIMITER.acquire(host)
        try:
            r = HL.requests.post(url, data=body_json, headers=headers, timeout=timeout)
            if r.status_code in HL.RETRY_STATUS:
                last_err = f"HTTP {r.status_code}"; time.sleep(min(2 ** attempt, 30)); continue
            body = r.content
            sha = HL._sha(body)
            sub = HL.BLOB_DIR / sha[:2]; sub.mkdir(parents=True, exist_ok=True); (sub / sha).write_bytes(body)
            cc.execute("INSERT OR REPLACE INTO http_cache (url_hash,url,host,status,blob_sha,bytes,content_type,fetched_at,error) VALUES (?,?,?,?,?,?,?,?,?)",
                       (uh, key, host, str(r.status_code), sha, len(body), r.headers.get("Content-Type", ""), HL._now(), None))
            cc.commit()
            HL._log_call(key, host, r.status_code, len(body), sha, False, purpose)
            return {"ok": r.status_code == 200, "status": r.status_code, "body": body, "from_cache": False, "url": key, "error": None}
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"; time.sleep(min(2 ** attempt, 30))
    HL._log_call(key, host, "ERR", 0, None, False, purpose)
    return {"ok": False, "status": "ERR", "body": None, "from_cache": False, "url": key, "error": last_err}


def batch(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def fetch_runs(study_accs, purpose="ext_hits_runs", n=5):
    out = []
    for b in batch(sorted(set(study_accs)), n):
        q = " OR ".join(f'study_accession="{a}"' for a in b)
        r = HL.ena_search("read_run", q, RUN_FIELDS, purpose=purpose)
        if r and r.strip():
            out.append(pd.read_csv(io.StringIO(r), sep="\t", dtype=str))
    if not out:
        return pd.DataFrame(columns=RUN_FIELDS)
    return pd.concat(out, ignore_index=True).drop_duplicates("run_accession")


def fetch_studies(study_accs, purpose="ext_hits_study", n=20):
    out = []
    for b in batch(sorted(set(study_accs)), n):
        q = " OR ".join(f'study_accession="{a}"' for a in b)
        r = HL.ena_search("study", q, SC.ENA_STUDY_FIELDS, purpose=purpose)
        if r and r.strip():
            out.append(pd.read_csv(io.StringIO(r), sep="\t", dtype=str))
    if not out:
        return pd.DataFrame(columns=SC.ENA_STUDY_FIELDS)
    return pd.concat(out, ignore_index=True).drop_duplicates("study_accession")


def _jcounts(s):
    return json.dumps(s.fillna("").value_counts().to_dict())


def build_hits(study_accs, channel, universe_acc, purpose="ext_hits"):
    """Return (studies_df, runs_df). channel: str or dict acc->str."""
    accs = sorted(set(study_accs))
    runs = fetch_runs(accs, purpose=purpose + "_runs")
    stud = fetch_studies(accs, purpose=purpose + "_study")
    rows = []
    for a in accs:
        rr = runs[runs.study_accession == a]
        sr = stud[stud.study_accession == a]
        title = sr.study_title.iloc[0] if len(sr) else (rr.study_title.iloc[0] if len(rr) and "study_title" in rr else "")
        ch = channel[a] if isinstance(channel, dict) else channel
        rows.append({
            "study_accession": a,
            "secondary_study_accession": sr.secondary_study_accession.iloc[0] if len(sr) else (rr.secondary_study_accession.iloc[0] if len(rr) else None),
            "study_title": title,
            "n_runs": int(len(rr)),
            "n_samples": int(rr.sample_accession.nunique()) if len(rr) else 0,
            "first_public": rr.first_public.min() if len(rr) else (sr.first_public.iloc[0] if len(sr) else None),
            "library_strategies": _jcounts(rr.library_strategy) if len(rr) else "{}",
            "library_sources": _jcounts(rr.library_source) if len(rr) else "{}",
            "host_tax_ids": "|".join(sorted(set(rr.host_tax_id.dropna()))) if len(rr) else "",
            "tax_ids": "|".join(sorted(set(rr.tax_id.dropna()))) if len(rr) else "",
            "scientific_names": "|".join(rr.scientific_name.fillna("").value_counts().head(5).index) if len(rr) else "",
            "discovery_channel": ch,
            "in_universe": bool(a in universe_acc or (len(sr) and sr.secondary_study_accession.iloc[0] in universe_acc)),
            "infant_title_hit": bool(INFANT_RE.search(str(title) or "")),
        })
    return pd.DataFrame(rows), runs

"""
harvest_lib -- the single outbound-HTTP layer for the Infant Shotgun Metagenome
Catalog.

Why this exists as one module: NCBI E-utilities returned HTTP 429 within a few
seconds of unthrottled querying from this sandbox. With agent fan-out running 48
children per wave, 48 children each hitting a live API would be throttled or
blocked outright. So the rule the whole pipeline is built on is:

    harvest centrally, once, into a local cache -- agents read the cache.

Every response is content-addressed on disk and every call is logged to
harvest_log in the catalog DB, which makes the harvest reproducible, resumable
after interruption, and free to re-run.
"""

from __future__ import annotations
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

import hashlib
import json
import os
import sqlite3
import threading
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import requests

import scope_constants as SC

# --------------------------------------------------------------------- paths

# R1-17 (2026-09-26): the cache dir is resolved from CATALOG_CACHE_DIR (default ~/catalog/cache; docs/DATA_LAYOUT.md) and
# created LAZILY on first use — importing this module from any cwd no longer creates harvest_cache/ there. A pre-existing
# ./harvest_cache in the cwd (the historical flat layout and the `make resweep` symlink) still wins for compatibility.
ROOT        = Path(".").resolve()
if (ROOT / "harvest_cache").exists():
    CACHE_DIR = ROOT / "harvest_cache"
else:
    CACHE_DIR = Path(os.environ.get("CATALOG_CACHE_DIR", "~/catalog/cache")).expanduser() / "harvest_cache"
BLOB_DIR    = CACHE_DIR / "blobs"
CATALOG_DB  = ROOT / "infant_metagenome_catalog.sqlite"
CACHE_DB    = CACHE_DIR / "http_cache.sqlite"
_DIRS_READY = False


def _ensure_dirs():
    global _DIRS_READY
    if not _DIRS_READY:
        for d in (CACHE_DIR, BLOB_DIR):
            d.mkdir(parents=True, exist_ok=True)
        _DIRS_READY = True

USER_AGENT = "infant-metagenome-catalog/1.0 (research metadata harvest)"

_local = threading.local()
_log_lock = threading.Lock()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _uhash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


# ------------------------------------------------------------ contact / keys

def contact_email():
    """User's contact address if the platform has one, else None."""
    try:
        import builtins
        h = getattr(builtins, "host", None)
        if h is None:
            return None
        return h.get_user_email()
    except Exception:
        return None


NCBI_API_KEY = os.environ.get("NCBI_API_KEY") or None


# ------------------------------------------------------------- rate limiting

class _HostLimiter:
    """Token bucket per host. Shared across threads in one process."""

    def __init__(self):
        self._buckets = {}
        self._lock = threading.Lock()

    def _cfg(self, host):
        cfg = dict(SC.RATE_LIMITS.get(host, SC.RATE_LIMITS["_default"]))
        if host == "eutils.ncbi.nlm.nih.gov" and NCBI_API_KEY:
            cfg["rps"] = SC.NCBI_RPS_WITH_KEY
        return cfg

    def acquire(self, host):
        while True:
            with self._lock:
                cfg = self._cfg(host)
                b = self._buckets.setdefault(host, {"tokens": cfg["burst"], "last": time.monotonic()})
                now = time.monotonic()
                b["tokens"] = min(cfg["burst"], b["tokens"] + (now - b["last"]) * cfg["rps"])
                b["last"] = now
                if b["tokens"] >= 1.0:
                    b["tokens"] -= 1.0
                    return
                deficit = (1.0 - b["tokens"]) / cfg["rps"]
            time.sleep(min(deficit, 2.0))


LIMITER = _HostLimiter()


# -------------------------------------------------------------- cache tables

_CACHE_DDL = """
CREATE TABLE IF NOT EXISTS http_cache (
    url_hash    TEXT PRIMARY KEY,
    url         TEXT NOT NULL,
    host        TEXT,
    status      TEXT,
    blob_sha    TEXT,
    bytes       INTEGER,
    content_type TEXT,
    fetched_at  TEXT,
    error       TEXT
);
CREATE INDEX IF NOT EXISTS ix_cache_host ON http_cache(host);
"""


def _cache_conn():
    c = getattr(_local, "cache", None)
    if c is None:
        _ensure_dirs()
        c = sqlite3.connect(CACHE_DB, timeout=60)
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(_CACHE_DDL)
        _local.cache = c
    return c


def catalog_conn():
    """Connection to the catalog DB (per-thread)."""
    c = getattr(_local, "catalog", None)
    if c is None:
        c = sqlite3.connect(CATALOG_DB, timeout=60)
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA foreign_keys=ON")
        _local.catalog = c
    return c


def init_catalog(schema_path="catalog_schema.sql"):
    con = sqlite3.connect(CATALOG_DB, timeout=60)
    con.executescript(Path(schema_path).read_text())
    con.commit()
    n = con.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table'"
    ).fetchone()[0]
    con.close()
    return n


def _log_call(url, host, status, nbytes, blob_sha, from_cache, purpose, error=None):
    try:
        with _log_lock:
            con = catalog_conn()
            con.execute(
                "INSERT INTO harvest_log (url,url_hash,host,http_status,bytes,"
                "response_sha256,from_cache,fetched_at,purpose,error) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (url, _uhash(url), host, str(status), nbytes, blob_sha,
                 int(from_cache), _now(), purpose, error),
            )
            con.commit()
    except Exception:
        pass  # logging must never break a harvest


# ------------------------------------------------------------------ core get

RETRY_STATUS = {429, 500, 502, 503, 504}


def fetch(url, purpose="unspecified", force=False, max_retries=5,
          timeout=180, expect="bytes"):
    """
    Rate-limited, cached, logged GET.

    Returns {'ok', 'status', 'body', 'from_cache', 'url', 'error'}.
    `body` is bytes; use fetch_json / fetch_text for convenience.
    Cached responses cost no network and no rate-limit tokens, so agents and
    re-runs read them freely.
    """
    host = urllib.parse.urlparse(url).netloc
    uh = _uhash(url)
    cc = _cache_conn()

    if not force:
        row = cc.execute(
            "SELECT status, blob_sha, bytes, error FROM http_cache WHERE url_hash=?", (uh,)
        ).fetchone()
        if row and row[1]:
            blob = BLOB_DIR / row[1][:2] / row[1]
            if blob.exists():
                _log_call(url, host, row[0], row[2], row[1], True, purpose)
                return {"ok": str(row[0]) == "200", "status": row[0],
                        "body": blob.read_bytes(), "from_cache": True,
                        "url": url, "error": row[3]}

    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    last_err = None
    for attempt in range(max_retries):
        LIMITER.acquire(host)
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code in RETRY_STATUS:
                last_err = f"HTTP {r.status_code}"
                time.sleep(min(2 ** attempt, 30))
                continue
            body = r.content
            sha = _sha(body)
            _ensure_dirs()
            sub = BLOB_DIR / sha[:2]
            sub.mkdir(parents=True, exist_ok=True)
            (sub / sha).write_bytes(body)
            cc.execute(
                "INSERT OR REPLACE INTO http_cache "
                "(url_hash,url,host,status,blob_sha,bytes,content_type,fetched_at,error) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (uh, url, host, str(r.status_code), sha, len(body),
                 r.headers.get("Content-Type", ""), _now(), None),
            )
            cc.commit()
            _log_call(url, host, r.status_code, len(body), sha, False, purpose)
            return {"ok": r.status_code == 200, "status": r.status_code,
                    "body": body, "from_cache": False, "url": url, "error": None}
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            time.sleep(min(2 ** attempt, 30))

    cc.execute(
        "INSERT OR REPLACE INTO http_cache "
        "(url_hash,url,host,status,blob_sha,bytes,content_type,fetched_at,error) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (uh, url, host, "ERR", None, 0, "", _now(), last_err),
    )
    cc.commit()
    _log_call(url, host, "ERR", 0, None, False, purpose, last_err)
    return {"ok": False, "status": "ERR", "body": b"", "from_cache": False,
            "url": url, "error": last_err}


def fetch_json(url, purpose="unspecified", **kw):
    r = fetch(url, purpose=purpose, **kw)
    if not r["ok"]:
        return None
    try:
        return json.loads(r["body"])
    except Exception:
        return None


def fetch_text(url, purpose="unspecified", **kw):
    r = fetch(url, purpose=purpose, **kw)
    return r["body"].decode("utf8", "replace") if r["ok"] else None


def fetch_many(urls, purpose="unspecified", workers=6, **kw):
    """Parallel fetch respecting per-host rate limits. Returns {url: result}."""
    from concurrent.futures import ThreadPoolExecutor
    out = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fetch, u, purpose=purpose, **kw): u for u in urls}
        for f in futs:
            u = futs[f]
            try:
                out[u] = f.result()
            except Exception as e:
                out[u] = {"ok": False, "status": "ERR", "body": b"",
                          "from_cache": False, "url": u, "error": str(e)}
    return out


# ----------------------------------------------------------------- ENA portal

ENA = "https://www.ebi.ac.uk/ena/portal/api"


def ena_count(result, query, purpose="ena_count"):
    url = f"{ENA}/count?result={result}&query={urllib.parse.quote(query)}"
    t = fetch_text(url, purpose=purpose)
    if t is None:
        return None
    for line in reversed(t.strip().splitlines()):
        line = line.strip()
        if line.isdigit():
            return int(line)
    return None


def ena_fields(result):
    url = f"{ENA}/searchFields?result={result}&format=json"
    d = fetch_json(url, purpose="ena_fields")
    return [f["columnId"] for f in d] if d else []


def ena_search(result, query, fields, limit=0, purpose="ena_search",
               fmt="tsv", offset=None, chunk=None):
    """
    ENA portal search. limit=0 means 'all matching records'.
    Returns raw TSV text (parse with pandas downstream).
    """
    q = urllib.parse.quote(query)
    f = ",".join(fields)
    url = f"{ENA}/search?result={result}&query={q}&fields={f}&limit={limit}&format={fmt}"
    if offset is not None:
        url += f"&offset={offset}"
    return fetch_text(url, purpose=purpose)


# ------------------------------------------------------------ NCBI E-utilities

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def _ncbi_suffix():
    s = ""
    if NCBI_API_KEY:
        s += f"&api_key={NCBI_API_KEY}"
    em = contact_email()
    if em:
        s += f"&email={urllib.parse.quote(em)}"
    s += "&tool=infant-metagenome-catalog"
    return s


def esearch(db, term, retmax=0, retstart=0, usehistory=False, purpose="esearch"):
    url = (f"{EUTILS}/esearch.fcgi?db={db}&term={urllib.parse.quote(term)}"
           f"&retmax={retmax}&retstart={retstart}&retmode=json"
           + ("&usehistory=y" if usehistory else "") + _ncbi_suffix())
    return fetch_json(url, purpose=purpose)


def esearch_count(db, term, purpose="esearch_count"):
    d = esearch(db, term, retmax=0, purpose=purpose)
    try:
        return int(d["esearchresult"]["count"])
    except Exception:
        return None


def esearch_all_ids(db, term, page=5000, purpose="esearch_ids", cap=200000):
    """Page through esearch collecting every UID."""
    total = esearch_count(db, term, purpose=purpose)
    if not total:
        return []
    ids, start = [], 0
    while start < min(total, cap):
        d = esearch(db, term, retmax=page, retstart=start, purpose=purpose)
        got = (d or {}).get("esearchresult", {}).get("idlist", [])
        if not got:
            break
        ids.extend(got)
        start += page
    return ids


def esummary(db, ids, purpose="esummary"):
    out = {}
    ids = list(ids)
    for i in range(0, len(ids), 200):
        chunk = ids[i:i + 200]
        url = (f"{EUTILS}/esummary.fcgi?db={db}&id={','.join(chunk)}"
               f"&retmode=json" + _ncbi_suffix())
        d = fetch_json(url, purpose=purpose)
        if d and "result" in d:
            for k, v in d["result"].items():
                if k != "uids":
                    out[k] = v
    return out


def efetch(db, ids, rettype="xml", retmode="xml", purpose="efetch", batch=200):
    """Yield raw response text per batch."""
    ids = list(ids)
    for i in range(0, len(ids), batch):
        chunk = ids[i:i + batch]
        url = (f"{EUTILS}/efetch.fcgi?db={db}&id={','.join(chunk)}"
               f"&rettype={rettype}&retmode={retmode}" + _ncbi_suffix())
        yield fetch_text(url, purpose=purpose)


def elink(dbfrom, db, ids, purpose="elink", batch=300):
    """
    dbfrom->db links. NOTE: E-utilities needs INTERNAL UIDs, not accession
    strings -- a live probe with a raw PRJNA number returned an empty linkset.
    Resolve accessions to UIDs with esearch first.
    """
    ids = list(ids)
    results = []
    for i in range(0, len(ids), batch):
        chunk = ids[i:i + batch]
        url = (f"{EUTILS}/elink.fcgi?dbfrom={dbfrom}&db={db}"
               f"&id={'&id='.join(chunk)}&retmode=json" + _ncbi_suffix())
        d = fetch_json(url, purpose=purpose)
        if d:
            results.extend(d.get("linksets", []))
    return results


def sra_runinfo(term, purpose="sra_runinfo"):
    """SRA runinfo CSV for a query -- one call gives run-level technical fields."""
    url = (f"{EUTILS}/efetch.fcgi?db=sra&rettype=runinfo&retmode=csv"
           f"&term={urllib.parse.quote(term)}" + _ncbi_suffix())
    return fetch_text(url, purpose=purpose)


# ------------------------------------------------------------------ Europe PMC

EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"


def epmc_search(query, page_size=1000, result_type="core", cursor="*",
                purpose="epmc_search"):
    url = (f"{EPMC}/search?query={urllib.parse.quote(query)}"
           f"&format=json&pageSize={page_size}&resultType={result_type}"
           f"&cursorMark={urllib.parse.quote(cursor)}")
    return fetch_json(url, purpose=purpose)


def epmc_search_all(query, page_size=1000, result_type="core", cap=100000,
                    purpose="epmc_search_all"):
    """Page through Europe PMC with cursorMark to exhaustion."""
    out, cursor, seen = [], "*", 0
    while True:
        d = epmc_search(query, page_size, result_type, cursor, purpose=purpose)
        if not d:
            break
        res = d.get("resultList", {}).get("result", [])
        out.extend(res)
        seen += len(res)
        nxt = d.get("nextCursorMark")
        if not res or not nxt or nxt == cursor or seen >= min(d.get("hitCount", 0), cap):
            break
        cursor = nxt
    return out


def epmc_count(query, purpose="epmc_count"):
    d = epmc_search(query, page_size=1, result_type="idlist", purpose=purpose)
    return d.get("hitCount") if d else None


def epmc_fulltext_xml(pmcid, purpose="epmc_fulltext"):
    pmcid = pmcid if str(pmcid).startswith("PMC") else f"PMC{pmcid}"
    return fetch(f"{EPMC}/{pmcid}/fullTextXML", purpose=purpose)


def epmc_supplementary_zip(pmcid, purpose="epmc_suppl"):
    pmcid = pmcid if str(pmcid).startswith("PMC") else f"PMC{pmcid}"
    return fetch(f"{EPMC}/{pmcid}/supplementaryFiles", purpose=purpose)


# ---------------------------------------------------------- other literature

def crossref(query=None, doi=None, rows=100, cursor=None, filt=None,
             purpose="crossref"):
    if doi:
        url = f"https://api.crossref.org/works/{urllib.parse.quote(doi)}"
    else:
        url = f"https://api.crossref.org/works?rows={rows}"
        if query:
            url += f"&query.bibliographic={urllib.parse.quote(query)}"
        if filt:
            url += f"&filter={urllib.parse.quote(filt)}"
        if cursor:
            url += f"&cursor={urllib.parse.quote(cursor)}"
    em = contact_email()
    if em:
        url += f"&mailto={urllib.parse.quote(em)}" if "?" in url else f"?mailto={urllib.parse.quote(em)}"
    return fetch_json(url, purpose=purpose)


def s2_search(query, limit=100, offset=0, fields=None, purpose="s2_search"):
    fields = fields or ["paperId", "externalIds", "title", "year", "venue",
                        "abstract", "isOpenAccess", "citationCount",
                        "publicationTypes"]
    url = (f"https://api.semanticscholar.org/graph/v1/paper/search"
           f"?query={urllib.parse.quote(query)}&limit={limit}&offset={offset}"
           f"&fields={','.join(fields)}")
    return fetch_json(url, purpose=purpose)


def s2_refs(paper_id, direction="references", limit=1000, purpose="s2_refs"):
    fields = "externalIds,title,year,venue,abstract,isOpenAccess"
    url = (f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}/"
           f"{direction}?limit={limit}&fields={urllib.parse.quote(fields)}")
    return fetch_json(url, purpose=purpose)


def biorxiv_details(server, doi, purpose="biorxiv"):
    return fetch_json(f"https://api.biorxiv.org/details/{server}/{doi}", purpose=purpose)


def mgnify(path, purpose="mgnify"):
    return fetch_json(f"https://www.ebi.ac.uk/metagenomics/api/v1/{path.lstrip('/')}",
                      purpose=purpose)


# ---------------------------------------------------------------- diagnostics

def cache_stats():
    cc = _cache_conn()
    row = cc.execute(
        "SELECT count(*), sum(bytes), sum(status='200'), sum(status='ERR') FROM http_cache"
    ).fetchone()
    per_host = cc.execute(
        "SELECT host, count(*), sum(bytes) FROM http_cache GROUP BY host ORDER BY 2 DESC"
    ).fetchall()
    return {"n_urls": row[0] or 0, "total_bytes": row[1] or 0,
            "n_ok": row[2] or 0, "n_err": row[3] or 0, "per_host": per_host}


def record_discovery(entity_type, entity_key, channel, query_id=None):
    con = catalog_conn()
    con.execute(
        "INSERT OR IGNORE INTO discovery_events "
        "(entity_type,entity_key,channel,query_id,seen_at) VALUES (?,?,?,?,?)",
        (entity_type, entity_key, channel, query_id, _now()),
    )
    con.commit()

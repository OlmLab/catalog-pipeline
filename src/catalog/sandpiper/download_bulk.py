"""Resume-safe streaming download of the Sandpiper 2.0.0 GTDB bulk condensed profiles from Zenodo.
Writes sp/sandpiper2.0.0.gtdb.csv.gz and sp/download_log.json (size, sha256, timings)."""
import requests, os, json, time, hashlib, sys
# --- catalog-pipeline shim (2026-09-26, R3-4): record id / version come from the environment so `make sandpiper-refresh
#     ZENODO_RECORD=<id> SANDPIPER_VERSION=<x.y.z>` can fetch a NEW Zenodo version; defaults = the 2026-09 snapshot. ---
ZENODO_RECORD = os.environ.get("SANDPIPER_ZENODO_RECORD", "20419175")
SPVER = os.environ.get("SANDPIPER_VERSION", "2.0.0")
FILE_KEY = os.environ.get("SANDPIPER_BULK_KEY", f"sandpiper{SPVER}.gtdb.csv.gz")
os.makedirs("sp", exist_ok=True)
URL = f"https://zenodo.org/api/records/{ZENODO_RECORD}/files/{FILE_KEY}/content"
OUT = f"sp/{FILE_KEY}"
LOG = "sp/download_log.json"
t0 = time.time()
have = os.path.getsize(OUT) if os.path.exists(OUT) else 0
rec = requests.get(f"https://zenodo.org/api/records/{ZENODO_RECORD}", timeout=60).json()
finfo = [f for f in rec["files"] if f["key"] == FILE_KEY][0]
total = int(finfo["size"]); zenodo_md5 = finfo["checksum"]
print("remote size", total, "have", have, flush=True)
attempt = 0
while have < total and attempt < 20:
    attempt += 1
    headers = {"Range": f"bytes={have}-"} if have else {}
    try:
        with requests.get(URL, headers=headers, stream=True, timeout=120, allow_redirects=True) as r:
            if have and r.status_code != 206:
                print("server ignored Range (status", r.status_code, ") — restarting from 0", flush=True)
                have = 0; mode = "wb"
            else:
                mode = "ab" if have else "wb"
            r.raise_for_status()
            with open(OUT, mode) as f:
                last = time.time()
                for chunk in r.iter_content(chunk_size=8 << 20):
                    f.write(chunk); have += len(chunk)
                    if time.time() - last > 30:
                        print(f"{have/1e9:.2f} GB / {total/1e9:.2f} GB  {time.time()-t0:.0f}s", flush=True); last = time.time()
    except Exception as e:
        print("attempt", attempt, "error", repr(e), flush=True); time.sleep(10)
        have = os.path.getsize(OUT) if os.path.exists(OUT) else 0
size = os.path.getsize(OUT)
h = hashlib.sha256(); m5 = hashlib.md5()
with open(OUT, "rb") as f:
    for b in iter(lambda: f.read(64 << 20), b""):
        h.update(b); m5.update(b)
log = {"url": URL, "zenodo_record": ZENODO_RECORD, "sandpiper_version": SPVER, "file": OUT,
       "content_length": total, "size_bytes": size, "sha256": h.hexdigest(), "md5": m5.hexdigest(), "zenodo_checksum": zenodo_md5, "md5_matches_zenodo": ("md5:"+m5.hexdigest())==zenodo_md5, "attempts": attempt,
       "seconds": round(time.time() - t0, 1), "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
       "complete": size == total}
json.dump(log, open(LOG, "w"), indent=1)
print(json.dumps(log), flush=True)

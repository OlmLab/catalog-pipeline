#!/usr/bin/env python
"""make_version.py — write VERSION.json for a data package (Reviewer A A7, Reviewer B B11).

One semver for the data package is the public version; release tags and site labels derive from it.

    VERSION.json = {
      "release_tag":        "data-v1.2.0",          # git tag the Actions release workflow reacts to
      "package_version":    "1.2.0",                # semver, from config/version.txt (or --package-version)
      "build_date":         "2026-09-26",           # package release date; the site footer uses THIS, never wall clock
      "generator_git_sha":  "<short sha or 'nogit'>",
      "generator_repo":     "OlmLab/catalog-pipeline",
      "tables": { "<file>": {"sha256": ..., "size_bytes": ..., "rows": <int|null>} , ... }
    }

Row counts: parquet from the file footer (no full read), csv/csv.gz by line count minus header.
``--check`` additionally asserts that the package README heading carries the same version
(``data package v1.2.0``) — the build_site.py regex must be ``v\\d+(?:\\.\\d+)*`` (A7) — and (R1-11) that EVERY
file in the package directory with a TABLE_EXT extension is listed in VERSION.json (unlisted files fail).

``--zip PATH`` (R1-11) writes a DETERMINISTIC zip after VERSION.json: python zipfile, ZIP_DEFLATED, entries sorted,
ZipInfo.date_time = build_date 00:00:00, external_attr 0o644 — byte-identical across rebuilds of identical content.
The zip's sha256 + size are written to ``PATH.sha256`` and to a sidecar ``<dirname(PATH)>/VERSION.json`` copy under
``package_zip`` (the in-zip VERSION.json cannot contain its own zip hash). ``--check --zip PATH`` verifies the sidecar.

Usage:
    python -m catalog.make_version --package build/package --build-date 2026-09-26 --zip build/data_package_v1.2.1.zip
    python -m catalog.make_version --package build/package --check [--zip build/data_package_v1.2.1.zip]
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
TABLE_EXT = (".parquet", ".csv", ".csv.gz", ".tsv", ".json", ".ipynb", ".md", ".sqlite")


def sha256_file(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def row_count(path: str):
    if path.endswith(".parquet"):
        try:
            import pyarrow.parquet as pq

            return pq.ParquetFile(path).metadata.num_rows
        except Exception:
            return None
    if path.endswith(".csv") or path.endswith(".tsv"):
        with open(path, "rb") as f:
            return max(sum(1 for _ in f) - 1, 0)
    if path.endswith(".csv.gz"):
        with gzip.open(path, "rb") as f:
            return max(sum(1 for _ in f) - 1, 0)
    return None


def git_sha(repo: str = REPO) -> str:
    try:
        return subprocess.check_output(["git", "-C", repo, "rev-parse", "--short", "HEAD"], text=True,
                                       stderr=subprocess.DEVNULL).strip() or "nogit"
    except Exception:
        return "nogit"


def read_version(repo: str = REPO) -> str:
    p = os.path.join(repo, "config", "version.txt")
    v = open(p).read().strip()
    if not SEMVER.match(v):
        raise SystemExit(f"config/version.txt must hold a semver (got {v!r})")
    return v


def build(package_dir: str, package_version: str, build_date: str | None = None, repo: str = REPO) -> dict:
    tables = {}
    for name in sorted(os.listdir(package_dir)):
        p = os.path.join(package_dir, name)
        if not os.path.isfile(p) or name == "VERSION.json" or not name.endswith(TABLE_EXT):
            continue
        tables[name] = dict(sha256=sha256_file(p), size_bytes=os.path.getsize(p), rows=row_count(p))
    return dict(release_tag=f"data-v{package_version}", package_version=package_version,
                build_date=build_date or dt.date.today().isoformat(), generator_git_sha=git_sha(repo),
                generator_repo="OlmLab/catalog-pipeline", tables=tables)


def build_zip(package_dir: str, out_zip: str, build_date: str) -> dict:
    """Deterministic zip of package_dir (files at the zip root, sorted, fixed timestamp). Returns {sha256, size_bytes, n_files}."""
    import zipfile

    y, m, d = (int(x) for x in build_date.split("-"))
    os.makedirs(os.path.dirname(os.path.abspath(out_zip)), exist_ok=True)
    if os.path.exists(out_zip):
        os.remove(out_zip)
    names = []
    for root, dirs, files in os.walk(package_dir):
        dirs.sort()
        for fn in files:
            if fn == ".DS_Store":
                continue
            names.append(os.path.relpath(os.path.join(root, fn), package_dir))
    names.sort()
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in names:
            zi = zipfile.ZipInfo(rel.replace(os.sep, "/"), date_time=(y, m, d, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            with open(os.path.join(package_dir, rel), "rb") as fh:
                zf.writestr(zi, fh.read())
    info = dict(sha256=sha256_file(out_zip), size_bytes=os.path.getsize(out_zip), n_files=len(names),
                zip_build="python zipfile, ZIP_DEFLATED, ZipInfo.date_time = build_date 00:00:00, external_attr 0o644, entries sorted")
    with open(out_zip + ".sha256", "w") as fh:
        fh.write(f"{info['sha256']}  {os.path.basename(out_zip)}\n")
    return info


def write_sidecar(package_dir: str, out_zip: str, zip_info: dict) -> str:
    """VERSION.json copy next to the zip, extended with package_zip = {filename, sha256, size_bytes} (R1-11)."""
    v = json.load(open(os.path.join(package_dir, "VERSION.json")))
    v["package_zip"] = dict(filename=os.path.basename(out_zip), **{k: zip_info[k] for k in ("sha256", "size_bytes", "n_files")})
    side = os.path.join(os.path.dirname(os.path.abspath(out_zip)), "VERSION.json")
    json.dump(v, open(side, "w"), indent=1, sort_keys=True)
    return side


def check(package_dir: str, package_version: str, out_zip: str | None = None) -> list[str]:
    problems = []
    readme = os.path.join(package_dir, "README.md")
    if os.path.exists(readme):
        m = re.search(r"data package v(\d+(?:\.\d+)*)", open(readme, encoding="utf-8").read())
        if not m:
            problems.append("README.md has no 'data package vX.Y.Z' heading")
        elif m.group(1) != package_version:
            problems.append(f"README.md says v{m.group(1)} but config/version.txt says {package_version}")
    vj = os.path.join(package_dir, "VERSION.json")
    if os.path.exists(vj):
        v = json.load(open(vj))
        if v.get("package_version") != package_version:
            problems.append(f"VERSION.json package_version {v.get('package_version')} != {package_version}")
        for name, meta in v.get("tables", {}).items():
            p = os.path.join(package_dir, name)
            if not os.path.exists(p):
                problems.append(f"{name} listed in VERSION.json but missing")
            elif sha256_file(p) != meta["sha256"]:
                problems.append(f"{name} sha256 differs from VERSION.json")
        # R1-11: every TABLE_EXT file present must be listed (a stale manifest passed --check before)
        listed = set(v.get("tables", {}))
        for name in sorted(os.listdir(package_dir)):
            p = os.path.join(package_dir, name)
            if os.path.isfile(p) and name != "VERSION.json" and name.endswith(TABLE_EXT) and name not in listed:
                problems.append(f"{name} present in the package but not listed in VERSION.json (regenerate VERSION.json last)")
    else:
        problems.append("VERSION.json missing")
    if out_zip:
        if not os.path.exists(out_zip):
            problems.append(f"{out_zip} missing")
        else:
            side = os.path.join(os.path.dirname(os.path.abspath(out_zip)), "VERSION.json")
            got = sha256_file(out_zip)
            if not os.path.exists(side):
                problems.append(f"sidecar {side} missing (run make_version --zip)")
            else:
                pz = json.load(open(side)).get("package_zip") or {}
                if pz.get("sha256") != got:
                    problems.append(f"zip sha256 {got[:12]} != sidecar package_zip.sha256 {str(pz.get('sha256'))[:12]}")
            sf = out_zip + ".sha256"
            if os.path.exists(sf) and open(sf).read().split()[0] != got:
                problems.append(f"{sf} does not match the zip")
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--package", required=True)
    ap.add_argument("--out", default=None, help="default <package>/VERSION.json")
    ap.add_argument("--package-version", default=None, help="override config/version.txt")
    ap.add_argument("--build-date", default=None, help="YYYY-MM-DD; default today (record it in CHANGELOG)")
    ap.add_argument("--check", action="store_true", help="verify README version, table hashes, unlisted files (+ zip sidecar with --zip); no write")
    ap.add_argument("--zip", default=None, help="also write the deterministic package zip here (+ .sha256 and sidecar VERSION.json)")
    a = ap.parse_args(argv)
    version = a.package_version or read_version()
    if a.check:
        probs = check(a.package, version, a.zip)
        print("\n".join(probs) if probs else f"OK: package {version} consistent")
        return 1 if probs else 0
    v = build(a.package, version, a.build_date)
    v["check_rule"] = "every file in the package directory with extension in TABLE_EXT must be listed in tables (unlisted files fail --check)"
    out = a.out or os.path.join(a.package, "VERSION.json")
    json.dump(v, open(out, "w"), indent=1, sort_keys=True)
    print(json.dumps({k: v[k] for k in ("release_tag", "package_version", "build_date", "generator_git_sha")} | {"n_tables": len(v["tables"])}))
    if a.zip:
        info = build_zip(a.package, a.zip, v["build_date"])
        side = write_sidecar(a.package, a.zip, info)
        print(json.dumps({"zip": a.zip, "sha256": info["sha256"], "size_bytes": info["size_bytes"], "sidecar": side}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

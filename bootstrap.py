#!/usr/bin/env python
"""bootstrap.py — make a fresh checkout (or a fresh Claude session) able to run a catalog cycle (A4).

Steps (each can be skipped with a flag):
  1. environment  : create/update the conda env from environment.yml (or pip -r requirements.lock into the
                    current interpreter with --pip).  Inside Claude Science the env already exists
                    (`infantcat`); pass --no-env.
  2. inputs       : materialise the DATA groups of config/inputs.json (every group except `code`, i.e. `data`,
                    `reports`, `sandpiper`, `authors`) into data/inputs/<filename>. Code entries are never copied —
                    they are verified in place by tests/test_inputs_hashes.py. Entries whose artifact_id starts with
                    `skill:` (vendored skill files) are skipped.
                    Source order: (a) an existing file in --data-root (default ~/catalog/data, then data/inputs),
                    (b) the artifact store when a `host` object is present (host.artifact_path(version_id)),
                    (c) otherwise reported as MISSING.  Every file is sha256-verified against inputs.json;
                    a mismatch is an error (never a warning) — see docs/RUNBOOK.md §0.
  3. tests        : python -m pytest tests -q (skipped when required inputs are missing — see exit codes).

Exit codes (R1-02): 0 ok · 2 conda missing · 3 sha256 mismatch · 4 a `required` input is MISSING · otherwise pytest's rc.
The MISSING list is printed BEFORE the test run so an empty data/inputs/ can never look like "tests green".

Usage (shell / subprocess — the artifact store is NOT reachable this way; files must be in --data-root):
    python bootstrap.py                       # everything
    python bootstrap.py --no-env --only-required
    python bootstrap.py --inputs-only --data-root ~/catalog/data

Usage inside a Claude Science python kernel (artifact store reachable through the kernel's `host` global):
    __file__ = "/path/to/catalog-pipeline/bootstrap.py"; exec(open(__file__).read()); sys.exit = lambda *_: None
    rc = main(["--no-env", "--only-required"])   # `host` is picked up from the kernel namespace
The kernel form is what `make bootstrap-kernel` prints; `python bootstrap.py` from the Makefile is the shell form.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
INPUTS = os.path.join(REPO, "config", "inputs.json")
CODE_GROUPS = {"code"}  # verified in place, never materialised


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def host_obj():
    """The platform `host` object if we run inside a Claude Science kernel (exec'd), else None.
    Order: an explicitly injected module global, builtins.host, then any caller frame's globals (R1-01 style)."""
    import builtins
    import inspect

    h = globals().get("host") or getattr(builtins, "host", None)
    if h is None:
        for fi in inspect.stack()[1:]:
            cand = fi.frame.f_globals.get("host")
            if cand is not None and callable(getattr(cand, "artifact_path", None)):
                h = cand
                break
    return h if h is not None and callable(getattr(h, "artifact_path", None)) else None


def step_env(pip: bool) -> None:
    if pip:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", os.path.join(REPO, "requirements.lock")])
        return
    if shutil.which("conda") is None:
        print("conda not found; use --pip or --no-env", file=sys.stderr)
        sys.exit(2)
    env_yml = os.path.join(REPO, "environment.yml")
    name = "infantcat"
    envs = subprocess.check_output(["conda", "env", "list"], text=True)
    verb = "update" if f"\n{name} " in envs or f"/{name}\n" in envs else "create"
    subprocess.check_call(["conda", "env", verb, "-n", name, "-f", env_yml] + (["--prune"] if verb == "update" else []))


def data_entries(cfg: dict, only_required: bool):
    """Yield (group, entry) for every materialisable input (all groups except code; skill: sources skipped)."""
    for group, entries in cfg["inputs"].items():
        if group in CODE_GROUPS:
            continue
        for e in entries:
            if str(e.get("artifact_id", "")).startswith("skill:"):
                continue
            if only_required and not e.get("required", True):
                continue
            yield group, e


def step_inputs(data_root: str, dest: str, only_required: bool, host=None) -> dict:
    cfg = json.load(open(INPUTS))
    os.makedirs(dest, exist_ok=True)
    h = host if host is not None else host_obj()
    report = {"ok": [], "missing": [], "missing_required": [], "hash_mismatch": [], "skipped": [], "source": "host" if h else "data-root only"}
    for group, e in data_entries(cfg, only_required):
        fn = e["filename"]
        sub = e.get("dest_subdir") or ("" if group == "data" else group)
        target = os.path.join(dest, sub, fn) if sub else os.path.join(dest, fn)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        src = None
        for cand in (os.path.join(data_root, sub, fn) if sub else os.path.join(data_root, fn), os.path.join(data_root, fn), target):
            if os.path.exists(cand):
                src = cand
                break
        if src is None and h is not None and e.get("version_id"):
            try:
                src = h.artifact_path(e["version_id"])
            except Exception as ex:  # noqa: BLE001
                print(f"  artifact fetch failed for {fn}: {ex}", file=sys.stderr)
        if src is None:
            report["missing"].append(f"{group}/{fn}")
            if e.get("required", True):
                report["missing_required"].append(f"{group}/{fn}")
            continue
        if os.path.abspath(src) != os.path.abspath(target):
            shutil.copy(src, target)
        got = sha256_file(target)
        if e.get("sha256") and got != e["sha256"]:
            report["hash_mismatch"].append(f"{fn}: expected {e['sha256'][:12]} got {got[:12]}")
        else:
            report["ok"].append(f"{group}/{fn}")
    return report


def step_tests() -> int:
    return subprocess.call([sys.executable, "-m", "pytest", os.path.join(REPO, "tests"), "-q"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-env", action="store_true")
    ap.add_argument("--pip", action="store_true", help="pip install -r requirements.lock instead of conda")
    ap.add_argument("--inputs-only", action="store_true")
    ap.add_argument("--only-required", action="store_true", help="skip inputs marked required: false")
    ap.add_argument("--data-root", default=os.path.expanduser("~/catalog/data"))
    ap.add_argument("--dest", default=os.path.join(REPO, "data", "inputs"))
    ap.add_argument("--no-tests", action="store_true")
    ap.add_argument("--allow-missing", action="store_true", help="do not exit 4 on missing required inputs (CI without data)")
    a = ap.parse_args(argv)
    if not a.no_env and not a.inputs_only:
        step_env(a.pip)
    rep = step_inputs(a.data_root, a.dest, a.only_required)
    print(json.dumps({k: (len(v) if k == "ok" else v) for k, v in rep.items()}, indent=1))
    if rep["missing_required"]:
        print("MISSING required inputs (place them under --data-root or run the kernel form of bootstrap.py so the "
              "artifact store is reachable):", file=sys.stderr)
        for m in rep["missing_required"]:
            print("  -", m, file=sys.stderr)
    print("disk: ~1 GB for package inputs; +~25 GB if the harvest cache (harvest_cache.tar.gz, working_data "
          "artifact, 9.7 GB) is untarred under ~/catalog/cache — do that only for enumeration/harvest stages")
    rc = 0
    if rep["hash_mismatch"]:
        rc = 3
    if rep["missing_required"] and not a.allow_missing:
        rc = max(rc, 4)
    if rc == 0 and not a.inputs_only and not a.no_tests:
        rc = max(rc, step_tests())
    elif rc:
        print(f"bootstrap: exit {rc} — tests NOT run", file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main())

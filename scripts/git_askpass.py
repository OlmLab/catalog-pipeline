#!/usr/bin/env python
"""git_askpass.py — hand the GitHub token to git without depending on an env-var name (R1-15).

Two modes:
  * as GIT_ASKPASS helper (git calls it with a prompt string): prints `x-access-token` for the username prompt and the
    token for the password prompt. The token is resolved, in order, from host.credentials.get('github')['token'] when a
    `host` object is available (Claude kernel), then from any of GITHUB_TOKEN / GH_TOKEN / CATALOG_GITHUB_TOKEN. Nothing is
    ever printed except to git's pipe; nothing is written to disk.
  * --check CLONE [CLONE ...]: runs `git ls-remote --heads origin` in every clone with GIT_ASKPASS set to this file and
    reports which repos are reachable (exit 1 on any failure). Records NOTHING about the token.

    GIT_ASKPASS=scripts/git_askpass.py git -C ~/catalog/infant-gut-catalog push origin release/1.2.1 site-v1.2.1
"""
from __future__ import annotations

import os
import subprocess
import sys

ENV_NAMES = ("GITHUB_TOKEN", "GH_TOKEN", "CATALOG_GITHUB_TOKEN")


def token() -> str | None:
    h = globals().get("host")
    if h is None:
        import builtins

        h = getattr(builtins, "host", None)
    if h is not None:
        for name in ("GitHub", "github"):  # stored 2026-09-26 under the display name "GitHub" (env var GITHUB_TOKEN)
            try:
                return h.credentials.get(name)["token"]
            except Exception:  # noqa: BLE001
                continue
    for n in ENV_NAMES:
        if os.environ.get(n):
            return os.environ[n]
    return None


def check(clones: list[str]) -> int:
    env = {**os.environ, "GIT_ASKPASS": os.path.abspath(__file__), "GIT_TERMINAL_PROMPT": "0"}
    rc = 0
    for c in clones:
        p = subprocess.run(["git", "-C", c, "ls-remote", "--heads", "origin"], env=env, capture_output=True, text=True)
        ok = p.returncode == 0
        print(f"{'OK ' if ok else 'FAIL'} {c}: {len(p.stdout.splitlines())} heads" if ok else f"FAIL {c}: {p.stderr.strip()[:160]}")
        rc |= 0 if ok else 1
    present = [n for n in ENV_NAMES if os.environ.get(n)]
    print("token source:", "host.credentials" if token() and not present else (present[0] if present else "NONE — declare credentials=['github'] on the cell or export one of " + "/".join(ENV_NAMES)))
    return rc


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--check":
        return check(argv[1:])
    prompt = " ".join(argv).lower()
    if "username" in prompt:
        print("x-access-token")
        return 0
    t = token()
    if not t:
        return 1
    print(t)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

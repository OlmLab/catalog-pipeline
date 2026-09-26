"""Runtime model resolution — config/models.yaml maps ROLES to model FAMILIES, never to ids.

Reviewer A finding A4(c): literal model ids hard-coded in scripts route to retired models once
the id is stale. Every LLM-calling script therefore asks ``resolve_model("<role>")`` at import
time and the id is looked up from the live platform:

    1. If the ``host`` object is available (Claude Science kernel), the role's ``resolver`` in
       models.yaml is applied: ``reasoning_model`` → host.reasoning_model(),
       ``current_model`` → host.current_model(), ``list_models`` → newest id in host.list_models()
       whose name matches the role's ``family_regex``.
    2. Otherwise the environment variable ``CATALOG_MODEL_<ROLE>`` (upper-case) is used —
       this is how CI or a plain shell supplies an id.
    3. Otherwise a ``ModelResolutionError`` is raised. There is no literal fallback on purpose.

The YAML file is parsed with PyYAML when available and with a tiny built-in reader otherwise
(the file is deliberately kept to a flat ``role: {key: value}`` structure so both agree).
"""
from __future__ import annotations

import builtins
import inspect
import os
import re
import sys
from functools import lru_cache
from typing import Any

# Explicitly registered host object (R1-01). In a Claude Science python kernel ``host`` is a
# kernel-namespace global — NOT builtins.host and NOT sys.modules['__main__'].__dict__ — so the
# script header must hand it over:  ``from catalog.models import set_host; set_host(globals().get("host"))``.
_HOST: Any = None

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_CFG = os.path.join(os.path.dirname(os.path.dirname(_HERE)), "config", "models.yaml")


class ModelResolutionError(RuntimeError):
    pass


def _read_models_yaml(path: str) -> dict[str, dict[str, Any]]:
    text = open(path, encoding="utf-8").read()
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
        return {k: v for k, v in (data.get("roles") or {}).items()}
    except ImportError:
        pass
    # minimal reader: expects "roles:" then two-space-indented role blocks with "key: value" lines
    roles: dict[str, dict[str, Any]] = {}
    cur = None
    in_roles = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if line.startswith("roles:"):
            in_roles = True
            continue
        if not in_roles:
            continue
        if re.match(r"^  \S.*:$", line):
            cur = line.strip()[:-1]
            roles[cur] = {}
        elif cur and re.match(r"^    \S", line):
            k, _, v = line.strip().partition(":")
            v = v.strip().strip("'\"")
            roles[cur][k.strip()] = v
        elif re.match(r"^\S", line):
            in_roles = False
    return roles


@lru_cache(maxsize=None)
def load_roles(path: str | None = None) -> dict[str, dict[str, Any]]:
    path = path or os.environ.get("CATALOG_MODELS_YAML", _DEFAULT_CFG)
    if not os.path.exists(path):
        raise ModelResolutionError(f"models.yaml not found at {path}; set CATALOG_MODELS_YAML")
    return _read_models_yaml(path)


def set_host(h: Any) -> Any:
    """Register the kernel ``host`` object for model resolution (idempotent; None is ignored)."""
    global _HOST
    if h is not None:
        _HOST = h
    return _HOST


def _looks_like_host(h: Any) -> bool:
    return h is not None and any(callable(getattr(h, m, None)) for m in ("list_models", "reasoning_model", "current_model"))


def _host():
    """Find the platform ``host`` object: set_host() > builtins > __main__ > caller frame globals."""
    if _looks_like_host(_HOST):
        return _HOST
    h = getattr(builtins, "host", None)
    if _looks_like_host(h):
        return h
    main = sys.modules.get("__main__")
    h = getattr(main, "__dict__", {}).get("host") if main is not None else None
    if _looks_like_host(h):
        return h
    # Fallback: the exec()'d script header lives in some caller frame whose globals hold ``host``
    # (kernel namespace). Scan outward; the first frame with a host-shaped object wins.
    try:
        for fi in inspect.stack()[1:]:
            cand = fi.frame.f_globals.get("host")
            if _looks_like_host(cand):
                return cand
            cand = fi.frame.f_locals.get("host") if fi.frame.f_locals is not fi.frame.f_globals else None
            if _looks_like_host(cand):
                return cand
    except Exception:  # noqa: BLE001 — stack inspection is best-effort
        pass
    return None


def _version_key(model_id: str):
    # sort by every integer group in the id so "…-5-1-…" beats "…-4-5-…"; then by string
    return ([int(x) for x in re.findall(r"\d+", model_id)], model_id)


def resolve_model(role: str, *, host: Any = None, roles: dict | None = None) -> str:
    """Return a live model id for a role defined in config/models.yaml (screen / rubric / …)."""
    roles = roles or load_roles()
    if role not in roles:
        raise ModelResolutionError(f"role {role!r} not in models.yaml (have {sorted(roles)})")
    spec = roles[role]
    env_key = f"CATALOG_MODEL_{role.upper()}"
    if os.environ.get(env_key):
        return os.environ[env_key]
    h = host or _host()
    if h is not None:
        resolver = spec.get("resolver", "list_models")
        fam = re.compile(spec.get("family_regex", "."), re.I)
        if resolver == "reasoning_model":
            mid = h.reasoning_model()
            if fam.search(mid):
                return mid
        elif resolver == "current_model":
            return h.current_model()
        cands = [m for m in h.list_models() if fam.search(m)]
        if cands:
            return sorted(cands, key=_version_key)[-1]
        raise ModelResolutionError(f"no model in host.list_models() matches {spec.get('family_regex')!r} for role {role!r}")
    raise ModelResolutionError(
        f"cannot resolve role {role!r}: no host object and {env_key} not set "
        "(run inside a Claude Science kernel or export the variable)"
    )


def main(argv: list[str] | None = None) -> int:
    """``python -m catalog.models [role ...]`` — print one line per role; exit 1 if ANY role is unresolved (R1-01)."""
    argv = sys.argv[1:] if argv is None else argv
    rc = 0
    for r in argv or sorted(load_roles()):
        try:
            print(r, resolve_model(r))
        except ModelResolutionError as e:
            print(r, "UNRESOLVED:", e)
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())

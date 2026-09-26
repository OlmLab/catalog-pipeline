"""A4(b): the validators exist in two places — the repo copy that scripts exec (src/catalog/triage/curation_kernel.py)
and the `infant-curation-rules` skill's kernel.py that every child agent loads. They must not drift.

The skill kernel is vendored under skills/infant-curation-rules/kernel.py by `make sync-skills` (a Claude session
runs host.skills.read("infant-curation-rules", path="kernel.py") — see docs/RUNBOOK.md §0). If the environment
variable CATALOG_SKILL_KERNEL points at a freshly exported kernel.py, that file is compared too.
"""
import ast
import hashlib
import os

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_KERNEL = os.path.join(REPO, "src", "catalog", "triage", "curation_kernel.py")
VENDORED_KERNEL = os.path.join(REPO, "skills", "infant-curation-rules", "kernel.py")
EXT_KERNEL = os.path.join(REPO, "src", "catalog", "triage", "curation_kernel_ext.py")


def _sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def _top_level_constants(path):
    tree = ast.parse(open(path, encoding="utf-8").read())
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                out[node.targets[0].id] = ast.literal_eval(node.value)
            except Exception:  # noqa: BLE001
                pass
    return out


def _functions(path):
    tree = ast.parse(open(path, encoding="utf-8").read())
    return {n.name: ast.dump(n.body[-1]) for n in tree.body if isinstance(n, ast.FunctionDef)}


def test_repo_kernel_equals_vendored_skill_kernel():
    assert os.path.exists(VENDORED_KERNEL), "run `make sync-skills` to vendor the skill kernel"
    assert _sha(REPO_KERNEL) == _sha(VENDORED_KERNEL), (
        "src/catalog/triage/curation_kernel.py differs from skills/infant-curation-rules/kernel.py — "
        "update the repo copy from the skill (the skill is canonical) or publish the skill from the repo copy")


def test_ext_kernel_shares_vocabularies_with_kernel():
    base = _top_level_constants(REPO_KERNEL)
    ext = _top_level_constants(EXT_KERNEL)
    for name in ("REASON_CODES", "OUTCOMES", "SOURCE_PREFIXES", "MAX_QUOTE_WORDS", "MAX_INFANT_AGE_DAYS"):
        assert name in base and name in ext, name
        assert tuple(base[name]) == tuple(ext[name]) if isinstance(base[name], (list, tuple)) else base[name] == ext[name], (
            f"{name} differs between curation_kernel.py and curation_kernel_ext.py")


def test_ext_kernel_is_superset_of_kernel_functions():
    base, ext = _functions(REPO_KERNEL), _functions(EXT_KERNEL)
    missing = set(base) - set(ext)
    assert not missing, f"curation_kernel_ext.py lacks {missing}"


@pytest.mark.skipif(not os.environ.get("CATALOG_SKILL_KERNEL"), reason="CATALOG_SKILL_KERNEL not set (export from host.skills.read)")
def test_repo_kernel_equals_live_skill_kernel():
    assert _sha(REPO_KERNEL) == _sha(os.environ["CATALOG_SKILL_KERNEL"])

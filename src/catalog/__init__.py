"""catalog — the Infant Gut Shotgun-Metagenome Catalog pipeline package.

Layout (src/catalog/):
    enumeration/  frame-free sweep, taxon-frame enumeration v3, monthly re-sweep, scope constants
    harvest/      cache-through HTTP (harvest_lib), literature harvest, accession mining, paper linking
    triage/       batched LLM judgment (llm_batch_common), Sonnet rubric/confirm, Haiku paper screen,
                  validators (curation_kernel[_ext].py == the infant-curation-rules skill kernel)
    extraction/   per-sample metadata routes R1–R4, merge, subject resolution, wide table, sample-unit fix
    prompts/      system prompts used by the LLM routes (*_system.txt)
    legacy/       superseded versions kept for provenance (v1/v2 enumeration, v1 scope constants)
    apply_findings.py, make_version.py, models.py   (new in the repo skeleton, 2026-09-26)

Every script was written to run flat from one working directory (``import harvest_lib``).
Importing this package registers each stage directory on ``sys.path`` so those flat imports
keep working when the scripts live in the package layout. Scripts carry a small header that
imports ``catalog`` (falling back to flat mode when the package is not importable).
"""
from __future__ import annotations

import os as _os
import sys as _sys

PKG_DIR = _os.path.dirname(_os.path.abspath(__file__))
SRC_DIR = _os.path.dirname(PKG_DIR)
REPO_DIR = _os.path.dirname(SRC_DIR)
CONFIG_DIR = _os.environ.get("CATALOG_CONFIG_DIR", _os.path.join(REPO_DIR, "config"))

STAGES = ("enumeration", "harvest", "triage", "extraction", "prompts", "legacy")


def register_stage_paths() -> list[str]:
    """Put src/catalog/<stage>/ (except legacy) on sys.path so flat sibling imports resolve.

    ``legacy`` is deliberately NOT registered: it holds superseded modules whose names collide
    with current ones (scope_constants v1/v2, enumerate_universe v1/v2)."""
    added = []
    for stage in STAGES:
        if stage == "legacy":
            continue
        p = _os.path.join(PKG_DIR, stage)
        if _os.path.isdir(p) and p not in _sys.path:
            _sys.path.append(p)
            added.append(p)
    return added


register_stage_paths()

from .models import resolve_model  # noqa: E402  (re-exported for the script header)

__all__ = ["PKG_DIR", "SRC_DIR", "REPO_DIR", "CONFIG_DIR", "STAGES", "register_stage_paths", "resolve_model"]
__version__ = "0.1.0"

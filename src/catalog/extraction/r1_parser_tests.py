"""Unit tests for r1_title_parser.parse_sample_name (R1' fix: DOL/day tokens beat subject ordinals).
Run: python r1_parser_tests.py
"""
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
import sys, os
# (sys.path handled by the repo layout shim above)
from r1_title_parser import parse_sample_name as P

CASES = [
    # PRJNA327106 titles (the bug: 'Infant 1 DOL 25' was read as 1 day)
    ("Infant 1 DOL 25 gut", 25, "1"),
    ("Infant 1 DOL 10 gut", 10, "1"),
    ("Infant 2 DOL 8 gut", 8, "2"),
    ("Infant 2 DOL 28 gut", 28, "2"),
    ("Infant 12 DOL 3 gut", 3, "12"),
    # PRJNA698986 titles
    ("Infant #59 DOL 256", 256, "59"),
    ("Infant #59 DOL 11", 11, "59"),
    # explicit unit words
    ("Stool sample collected at the age of 6 months from subject R15", 183, None),
    ("Stool sample collected at the age of 18 months from subject R15", 548, None),
    ("Stool sample collected near birth from subject R255", 0, None),
    ("M0059-Child:14 days", 14, None),
    ("M0059-Child:1 month", 30, None),
    ("Family T0150, Twin A, 7 month timepoint", 213, None),
    ("Family T0173, Twin B, 0 month timepoint", 0, None),
    ("Subject 4 day 3", 3, "4"),
    ("PND3_baby7", 3, None),
    ("postnatal day 12", 12, None),
    ("day_of_life_40", 40, None),
    ("NCS-053-Meconium_microbiome", 0, None),
    # compact letters
    ("WGS_unpaired_2-D6", 6, None),
    ("133_4M", 122, None),
    ("ARG_M4", 122, None),
    ("R15_6m_WMS", 183, None),
    # negatives: ordinals / timepoints / maternal are not ages
    ("11405.subject114.timepoint2", None, "114"),
    ("Infant 7 gut", None, "7"),
    ("M0059-Mother:Gest", None, None),
    ("C009V5", None, None),
    ("513122_6", None, None),
    ("T0150A_7", None, None),
    ("CM_colombia", None, None),
]


def run():
    fails = []
    for text, exp_age, exp_subj in CASES:
        r = P(text)
        if r["age_days"] != exp_age or (exp_subj is not None and r["subject_id"] != exp_subj):
            fails.append((text, exp_age, exp_subj, r["age_days"], r["subject_id"], r["tag"]))
    print(f"{len(CASES) - len(fails)}/{len(CASES)} passed")
    for f in fails:
        print("FAIL", f)
    return not fails


if __name__ == "__main__":
    sys.exit(0 if run() else 1)

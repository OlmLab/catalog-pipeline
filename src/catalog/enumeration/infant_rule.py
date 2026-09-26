"""Deterministic infant rule for BioSample-attribute sweep (no LLM).
parse_age_months(text) -> (months|None, unit_tag, note)
text_hit(text) -> matched span or ''
animal_hit(text) -> matched span or ''
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
import re

NULLS = {"", "missing", "not collected", "not applicable", "na", "n/a", "none", "unknown", "not provided",
         "missing: restricted access", "restricted access", "not available", "nan", "null", "-", "missing: not provided",
         "missing: not collected", "missing: not applicable", "unspecified", "not determined", "nd"}
UNIT_M = {"d": 1 / 30.4375, "day": 1 / 30.4375, "days": 1 / 30.4375, "dy": 1 / 30.4375, "dd": 1 / 30.4375,
          "w": 1 / 4.348, "wk": 1 / 4.348, "wks": 1 / 4.348, "week": 1 / 4.348, "weeks": 1 / 4.348,
          "m": 1.0, "mo": 1.0, "mos": 1.0, "mon": 1.0, "mons": 1.0, "month": 1.0, "months": 1.0, "mth": 1.0, "mths": 1.0,
          "y": 12.0, "yr": 12.0, "yrs": 12.0, "year": 12.0, "years": 12.0, "yo": 12.0, "y.o.": 12.0,
          "h": 1 / 730.5, "hr": 1 / 730.5, "hrs": 1 / 730.5, "hour": 1 / 730.5, "hours": 1 / 730.5}
NUM = r"(\d+(?:\.\d+)?)"
UNITS = r"(days?|dd|dy|d|weeks?|wks?|w|months?|mons?|mos?|mths?|m|years?|yrs?|yo|y\.o\.|y|hours?|hrs?|h)"
RE_ISO = re.compile(r"^P(?:(\d+(?:\.\d+)?)Y)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)W)?(?:(\d+(?:\.\d+)?)D)?(?:T(\d+)H)?$", re.I)
RE_NUM_UNIT = re.compile(rf"{NUM}\s*-?\s*{UNITS}\b\.?", re.I)
RE_RANGE = re.compile(rf"{NUM}\s*(?:-|–|to)\s*{NUM}\s*{UNITS}\b", re.I)
RE_UNIT_NUM = re.compile(rf"\b(day|week|month|year|dol|pma|dpb|dpp)\s*[:=#]?\s*{NUM}\b", re.I)
RE_BARE = re.compile(rf"^\s*{NUM}\s*$")
WORD_AGE = {"newborn": 0.0, "neonate": 0.25, "neonatal": 0.25, "birth": 0.0, "meconium": 0.0, "infant": 6.0, "toddler": 24.0, "baby": 6.0}
RE_TEXT = re.compile(r"\b(infants?\b(?!is)|neonat\w*|newborns?|pre-?terms?|prematur\w*|toddlers?|meconium|NICU|babies|baby|"
                     r"\d+(?:\.\d+)?\s?(?:-\s?)?(?:day|week|month)s?[- ]old|"
                     r"(?:day|week|month)s?\s?\d*\s?[- ]?of[- ]life|postnatal[- ]day|day of life)", re.I)
RE_ANIMAL = re.compile(r"\b(mouse|mice|murine|rats?|rodent|pigs?|piglets?|swine|porcine|sow|calf|calves|bovine|cattle|cow|"
                       r"lambs?|sheep|ovine|goats?|chick(?:s|en|ens)?|broilers?|poultry|foals?|equine|horses?|pupp(?:y|ies)|"
                       r"canine|dogs?|kittens?|feline|cats?|macaques?|monkeys?|primates?|rhesus|marmosets?|zebrafish|fish|"
                       r"rabbits?|hamsters?|guinea|ferrets?|bats?|larva[el]?|seedlings?|chickens?)\b", re.I)
# "premature" false positives in human adult contexts
RE_PREMATURE_FP = re.compile(r"premature (ovarian|menopause|aging|ageing|ejaculation|death|coronary|atherosclerosis|"
                             r"senescence|stop|termination|greying|graying|birth history)", re.I)


def _to_months(v, unit):
    return float(v) * UNIT_M[unit.lower()]


def parse_age_months(text):
    """Returns (months or None, unit_tag, note). unit_tag in
    {'iso','num_unit','range','unit_num','word','bare_assumed_years','none'}"""
    if text is None:
        return None, "none", ""
    s = str(text).strip()
    if s.lower() in NULLS:
        return None, "none", ""
    m = RE_ISO.match(s)
    if m and any(m.groups()):
        y, mo, w, d, h = m.groups()
        months = (float(y or 0) * 12 + float(mo or 0) + float(w or 0) / 4.348 + float(d or 0) / 30.4375 + float(h or 0) / 730.5)
        return months, "iso", s
    m = RE_RANGE.search(s)
    if m:
        a, b, u = m.groups()
        lo, hi = _to_months(a, u), _to_months(b, u)
        return hi, "range", f"{lo:.1f}-{hi:.1f}m"
    hits = RE_NUM_UNIT.findall(s)
    if hits:
        months = 0.0
        for v, u in hits:
            months += _to_months(v, u)
        return months, "num_unit", s
    m = RE_UNIT_NUM.search(s)
    if m:
        u, v = m.groups()
        u = {"dol": "day", "pma": "week", "dpb": "day", "dpp": "day"}.get(u.lower(), u.lower())
        return _to_months(v, u), "unit_num", s
    low = s.lower()
    for w, v in WORD_AGE.items():
        if re.search(rf"\b{w}\b", low):
            return v, "word", s
    m = RE_BARE.match(s)
    if m:
        v = float(m.group(1))
        return v * 12.0, "bare_assumed_years", s
    return None, "unparsed", s


def text_hit(text):
    if not text:
        return ""
    m = RE_TEXT.search(str(text))
    if not m:
        return ""
    if m.group(0).lower().startswith("prematur") and RE_PREMATURE_FP.search(str(text)):
        return ""
    return m.group(0)


def animal_hit(text):
    if not text:
        return ""
    m = RE_ANIMAL.search(str(text))
    return m.group(0) if m else ""


if __name__ == "__main__":
    for t in ["P3M", "P14D", "P2Y6M", "3 months", "12 weeks", "5 days", "2 years", "1y", "18 mos", "0-3 months", "6-12 months",
              "2-5 years", "newborn", "adult", "2", "0.5", "36 months", "37 months", "Missing: Restricted access", "day 7", "DOL 12",
              "4m", "3 wk", "6-month-old", "10 weeks", "60"]:
        print(t, "->", parse_age_months(t))
    for t in ["Bifidobacterium longum subsp. infantis", "Salmonella Infantis", "infant stool", "3-month-old infant", "mouse pup gut",
              "premature ovarian failure", "NICU stool", "day 14 of life", "Preterm infant"]:
        print(t, "->", text_hit(t), "|", animal_hit(t))

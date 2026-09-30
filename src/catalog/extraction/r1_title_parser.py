"""R1' sample-name (title / library_name) parser for the infant catalog.

Precedence (fix for the PRJNA327106 bug 'Infant 1 DOL 25' -> 1 day):
  1. explicit age tokens with a unit word ANYWHERE in the string:  DOL 25 | day 25 | 25 days |
     PND3 | postnatal day 3 | day_of_life 25 | 6 months | 3 weeks | 'age of 6 months'
  2. compact unit letters glued to a number:  D25 | 25D | 6M | M6 | _3M | W4 | 4W | 6m | 18mo
  3. birth words: birth | meconium | newborn | near birth -> 0 days
  4. subject ordinals ('Infant 1', 'Subject 12', '#59', 'Twin A', 'Family T0150') are NEVER ages;
     'timepoint2' / 'T2' / 'V4' are timepoint labels only (unit unknown -> no age).
  5. 'Gest' / 'gestation' / 'prenatal' / 'trimester' -> maternal prenatal sample, no infant age.
Returns dict(age_days, unit, number, tag, timepoint_label, subject_id, is_mother).
"""
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
import re

FACT = {"hours": 1 / 24.0, "days": 1.0, "weeks": 7.0, "months": 30.4375, "years": 365.25}
_UNIT_WORD = {"hour": "hours", "hours": "hours", "hr": "hours", "hrs": "hours",
              "day": "days", "days": "days", "dol": "days", "pnd": "days", "d": "days",
              "week": "weeks", "weeks": "weeks", "wk": "weeks", "wks": "weeks", "w": "weeks",
              "month": "months", "months": "months", "mo": "months", "mos": "months", "mon": "months", "m": "months",
              "year": "years", "years": "years", "yr": "years", "yrs": "years", "y": "years"}
NUM = r"(\d{1,4}(?:\.\d+)?)"

# 1. explicit unit words (either order), whole-word bounded
RX_UNIT_FIRST = re.compile(r"(?<![A-Za-z0-9])(?:DOL|dol|Dol|PND|pnd|day[ _-]?of[ _-]?life|postnatal[ _-]?day|post-natal[ _-]?day|day|Day|DAY|days|Days|week|Week|weeks|Weeks|month|Month|months|Months|year|years)[ _:\-]*" + NUM + r"(?![A-Za-z0-9])")
RX_NUM_FIRST = re.compile(r"(?<![A-Za-z0-9.])" + NUM + r"[ _-]?(days?|dol|DOL|weeks?|wks?|months?|mos?|mon|years?|yrs?|hours?|hrs?)(?![A-Za-z0-9])", re.I)
# 2. compact letter units  D25 / 25D / 6M / M6 / W4 / 4W / 18mo
RX_COMPACT_LETTER_FIRST = re.compile(r"(?<![A-Za-z0-9])([DdMmWw])[ _-]?(\d{1,3})(?![A-Za-z0-9.])")
RX_COMPACT_NUM_FIRST = re.compile(r"(?<![A-Za-z0-9.])(\d{1,3})[ _-]?([DdMmWw])(?![A-Za-z0-9])")
RX_BIRTH = re.compile(r"(?<![A-Za-z0-9])(meconium|newborn|at birth|near birth|birth|day 0|d0)(?![A-Za-z0-9])", re.I)
RX_SUBJECT = re.compile(r"(?<![A-Za-z0-9])(?:infant|subject|baby|child|participant|patient|kid|id)\s*#?\s*(\d{1,4})(?![A-Za-z0-9])", re.I)
RX_HASH_SUBJECT = re.compile(r"#\s*(\d{1,4})")
RX_TIMEPOINT = re.compile(r"(?<![A-Za-z0-9])(?:timepoint|time[ _-]?point|tp|visit|t|v)[ _-]?(\d{1,2})(?![A-Za-z0-9])", re.I)
RX_MOTHER = re.compile(r"(?<![A-Za-z])(mother|maternal|mom|gest\b|gestation|prenatal|pregnan|trimester)", re.I)


def _to_days(n, unit):
    d = float(n) * FACT[unit]
    return int(round(d))


def parse_sample_name(text):
    out = dict(age_days=None, unit=None, number=None, tag=None, timepoint_label=None, subject_id=None, is_mother=False)
    if text is None:
        return out
    s = str(text).strip()
    if not s:
        return out
    if RX_MOTHER.search(s):
        out["is_mother"] = True
    m = RX_SUBJECT.search(s) or RX_HASH_SUBJECT.search(s)
    if m:
        out["subject_id"] = m.group(1)
    # strip subject spans so their digits cannot be read as ages
    scrub = RX_SUBJECT.sub(" ", s)
    scrub = RX_HASH_SUBJECT.sub(" ", scrub)
    # timepoint labels (never an age by themselves)
    mt = RX_TIMEPOINT.search(scrub)
    if mt:
        out["timepoint_label"] = mt.group(0).strip()
    # 1. explicit unit words
    m = RX_UNIT_FIRST.search(scrub)
    if m:
        uw = re.match(r"[A-Za-z][A-Za-z _-]*?(?=[ _:\-]*\d)", m.group(0)).group(0).strip().lower()
        unit = "days" if ("day" in uw or uw in ("dol", "pnd")) else _UNIT_WORD.get(uw.split()[0], None)
        if unit:
            out.update(age_days=_to_days(m.group(1), unit), unit=unit, number=float(m.group(1)), tag="unit_word", timepoint_label=out["timepoint_label"] or m.group(0).strip())
            if out["is_mother"] and RX_MOTHER.search(s).group(1).lower().startswith("gest"):
                out.update(age_days=None, tag="gestational_maternal")
            return out
    m = RX_NUM_FIRST.search(scrub)
    if m:
        unit = _UNIT_WORD[m.group(2).lower().rstrip("s") if m.group(2).lower() not in _UNIT_WORD else m.group(2).lower()]
        out.update(age_days=_to_days(m.group(1), unit), unit=unit, number=float(m.group(1)), tag="unit_word", timepoint_label=out["timepoint_label"] or m.group(0).strip())
        return out
    # 3. birth words
    m = RX_BIRTH.search(scrub)
    if m and not out["is_mother"]:
        out.update(age_days=0, unit="days", number=0.0, tag="birth_word", timepoint_label=m.group(1))
        return out
    # 2. compact letters (lower confidence; caller decides)
    m = RX_COMPACT_LETTER_FIRST.search(scrub) or RX_COMPACT_NUM_FIRST.search(scrub)
    if m:
        letter, num = (m.group(1), m.group(2)) if m.group(1).isalpha() else (m.group(2), m.group(1))
        unit = _UNIT_WORD[letter.lower()]
        out.update(age_days=_to_days(num, unit), unit=unit, number=float(num), tag="compact_letter", timepoint_label=out["timepoint_label"] or m.group(0).strip())
        return out
    if out["is_mother"] and re.search(r"gest", s, re.I):
        out["tag"] = "gestational_maternal"
    return out

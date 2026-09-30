"""Score determinations against gold_extract (18 gold studies). Gold values are read ONLY here, for scoring."""
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
import pandas as pd, numpy as np

GOLD_MAP = {
    "age_at_collection_days": ("age_days", None),
    "delivery_mode": ("born_method", {"Vaginal Delivery": "vaginal", "Elective Cesarean Delivery": "c_section_elective", "Cesarean Section": "c_section", "Emergency Cesarean Delivery": "c_section_emergency"}),
    "feeding_mode": ("feeding_practice", {"Exclusively Breastfeeding": "exclusive_breast", "Mixed Feeding": "mixed", "No Breastfeeding": "formula", "Exclusively Formula Feeding": "formula"}),
    "preterm_status": ("premature", {"Term Birth": "term", "Preterm Birth": "preterm"}),
    "antibiotic_exposure": ("antibiotics_current_use", {"Yes": "yes", "No": "no"}),
    "gestational_age_weeks": ("gestational_age", None),
}
CS = {"c_section", "c_section_elective", "c_section_emergency"}


def gold_long(gold):
    rows = []
    for f, (gc, m) in GOLD_MAP.items():
        g = gold[["sample_key", "study_accession", gc, "age_days_source", "age_resolution"]].dropna(subset=["sample_key", gc]).copy()
        if m is not None:
            g = g[g[gc].isin(m)]
            g["gold_value"] = g[gc].map(m)
        else:
            g["gold_value"] = pd.to_numeric(g[gc], errors="coerce")
            g = g.dropna(subset=["gold_value"])
        g["field_name"] = f
        g["low_res"] = (f == "age_at_collection_days") & ((g.age_days_source == "cmd.age(unit_absent->Year)") | ((g.gold_value == 0) & (g.age_resolution == "numeric")))
        rows.append(g[["sample_key", "study_accession", "field_name", "gold_value", "low_res"]])
    return pd.concat(rows, ignore_index=True)


def agree(field, ours, gold):
    if field == "age_at_collection_days":
        try:
            a, b = float(ours), float(gold)
        except (TypeError, ValueError):
            return False
        return abs(a - b) <= max(7.0, 0.1 * max(a, b))
    if field == "gestational_age_weeks":
        try:
            return abs(float(ours) - float(gold)) <= 1.0
        except (TypeError, ValueError):
            return False
    if field == "delivery_mode":
        return ours == gold or (ours == "c_section" and gold in CS) or (gold == "c_section" and ours in CS)
    return ours == gold


def score(det, gl, by=("field_name",)):
    """det: determinations with sample_key, field_name, value_normalized, route. Returns per-group coverage/precision (all, excl. low_res)."""
    m = gl.merge(det[["sample_key", "field_name", "value_normalized", "route", "confidence", "evidence_quote", "evidence_source"]], on=["sample_key", "field_name"], how="left")
    m["covered"] = m.value_normalized.notna()
    m["agree"] = [agree(f, o, g) if c else False for f, o, g, c in zip(m.field_name, m.value_normalized, m.gold_value, m.covered)]
    out = []
    for k, g in m.groupby(list(by)):
        c = g[g.covered]
        ch = c[~c.low_res]
        out.append(dict(**dict(zip(by, k if isinstance(k, tuple) else (k,))), n_gold=len(g), n_covered=int(g.covered.sum()), coverage=round(g.covered.mean(), 3),
                        n_agree=int(c.agree.sum()), precision=round(c.agree.mean(), 3) if len(c) else np.nan,
                        n_covered_hires=len(ch), precision_hires=round(ch.agree.mean(), 3) if len(ch) else np.nan,
                        recall_hires=round(ch.agree.sum() / max(1, (~g.low_res).sum()), 3)))
    return pd.DataFrame(out), m

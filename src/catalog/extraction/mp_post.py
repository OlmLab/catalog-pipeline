"""Post-processing for the multi-paper R3 track: skill group-statement rules, consistency check,
R1/R2 gap restriction, Opus audit. Statements are dicts as produced by r3_p2_driver.run_requests."""
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
import re, json
import pandas as pd, numpy as np

NUMERIC = {"age_at_collection_days", "gestational_age_weeks", "birth_weight_grams"}
RX = {
    "exclusion_criterion": re.compile(r"\b(exclu\w*|eligib\w*|inclusion criteri\w*|were not eligible|not an exclusion)\b", re.I),
    "care_setting": re.compile(r"\b(NICU|neonatal intensive care|routinely|protocol|guideline|policy|standard (of )?care|hospital practice|unit'?s practice|prophyla\w+ (is|was|were) (given|administered))\b", re.I),
    "summary_word": re.compile(r"\b(predominantly|mostly|most|majority|common(ly)?|median|mean|average|approximately|about|\d+(\.\d+)?\s?%|percent|proportion|rate of)\b", re.I),
    "threshold": re.compile(r"(<|>|≤|≥|less than|more than|greater than|prior to|before \d|under \d|over \d|at least|minimum|maximum|below|above|between|\d+\s?[-–]\s?\d+\s?(weeks|wk|days|months|g\b|grams)|or (more|less|fewer))", re.I),
    "single_case": re.compile(r"\b(one|a single|two|three) (infant|child|participant|subject|patient|case|neonate)s?\b", re.I),
    "maternal_pregnancy": re.compile(r"\b(pregnan\w*|trimester|weeks? of (pregnancy|gestation) (sampl|collect)|gestational week\w* (sampl|collect)|antenatal|prenatal (sampl|visit))\b", re.I),
    "antiretroviral": re.compile(r"\b(antiretroviral|ART\b|HAART|nevirapine|zidovudine)", re.I),
    "healthy_only": re.compile(r"\bhealthy\b", re.I),
    "term_word": re.compile(r"\b(term|full-term|full term|37|38|39|40)\b", re.I),
    "nec_word": re.compile(r"\b(necroti[sz]ing|NEC)\b", re.I),
    "timepoint_list": re.compile(r"(\d+\s?,\s?\d+|\d+\s?(and|or|to)\s?\d+|\d+\s?[-–]\s?\d+)", re.I),
}


def rule_flags(s):
    """Return list of skill Rule-4 violations for a statement dict (empty = passes)."""
    a = s.get("applies_to") or {}
    typ = a.get("type")
    field = s.get("field"); val = str(s.get("value_normalized", ""))
    q = " ".join([str(s.get("quote", "")), str(s.get("value_raw", "") or "")])
    note = str(s.get("note", "") or "")
    flags = []
    if typ == "subgroup":
        return ["subgroup_not_expandable"]
    if RX["exclusion_criterion"].search(q) or RX["exclusion_criterion"].search(note):
        flags.append("eligibility_or_exclusion_criterion")
    if RX["care_setting"].search(q):
        flags.append("care_setting_or_policy")
    if RX["summary_word"].search(q):
        flags.append("summary_word")
    if field in NUMERIC or field == "preterm_status":
        if RX["threshold"].search(q):
            flags.append("threshold_or_range")
    if field == "preterm_status" and val == "term" and RX["healthy_only"].search(q) and not RX["term_word"].search(q):
        flags.append("healthy_implies_term")
    if typ == "all" and RX["single_case"].search(q):
        flags.append("single_case_applied_cohort_wide")
    if field == "gestational_age_weeks" and RX["maternal_pregnancy"].search(q):
        flags.append("maternal_pregnancy_weeks")
    if field in ("antibiotic_exposure", "maternal_antibiotics") and RX["antiretroviral"].search(q):
        flags.append("antiretroviral_not_antibiotic")
    if field == "nec_status" and val == "no" and not RX["nec_word"].search(q):
        flags.append("nec_no_without_nec_mention")
    if field == "age_at_collection_days" and typ == "all" and RX["timepoint_list"].search(q):
        flags.append("timepoint_list_as_single_age")
    if typ == "pattern" and a.get("regex", "") in ("", ".*", "^.*$", ".+"):
        flags.append("pattern_matches_everything")
    return flags


def _agree(field, a, b):
    try:
        if field == "age_at_collection_days":
            return abs(float(a) - float(b)) <= 14
        if field == "gestational_age_weeks":
            return abs(float(a) - float(b)) <= 1.0
        if field == "birth_weight_grams":
            return abs(float(a) - float(b)) <= 250
    except (TypeError, ValueError):
        return False
    return str(a).strip().casefold() == str(b).strip().casefold()


def consistency_check(det, existing, min_overlap=5, max_disagree=0.20):
    """det: expanded rows with a 'stmt_id' column; existing: R1/R2 per-sample rows (sample_key, field_name, value_normalized).
    Returns (kept_det, per-statement DataFrame)."""
    ex = existing.drop_duplicates(["sample_key", "field_name"])[["sample_key", "field_name", "value_normalized"]].rename(columns={"value_normalized": "ex_val"})
    m = det.merge(ex, on=["sample_key", "field_name"], how="left")
    m["overlap"] = m.ex_val.notna()
    m["agree"] = [(_agree(f, a, b) if pd.notna(b) else np.nan) for f, a, b in zip(m.field_name, m.value_normalized, m.ex_val)]
    g = m.groupby("stmt_id").agg(n_rows=("sample_key", "size"), n_overlap=("overlap", "sum"), n_agree=("agree", lambda x: int(np.nansum(x.astype(float)))))
    g["disagree_frac"] = np.where(g.n_overlap > 0, 1 - g.n_agree / g.n_overlap.clip(lower=1), np.nan)
    g["drop"] = (g.n_overlap >= min_overlap) & (g.disagree_frac > max_disagree)
    keep_ids = set(g.index[~g["drop"]])
    return det[det.stmt_id.isin(keep_ids)].copy(), g.reset_index()


AUDIT_TOOL = {"name": "statement_audit", "description": "Audit verdicts for group-level metadata statements.",
              "input_schema": {"type": "object", "properties": {"verdicts": {"type": "array", "items": {"type": "object", "properties": {
                  "stmt_id": {"type": "string"}, "verdict": {"type": "string", "enum": ["keep", "downgrade", "drop"]},
                  "reason": {"type": "string"}}, "required": ["stmt_id", "verdict", "reason"]}}}, "required": ["verdicts"]}}

AUDIT_SYSTEM = """You audit GROUP-LEVEL metadata statements extracted from papers about infant gut metagenome cohorts before they are propagated to every sample of the cohort (or of a timepoint / name pattern). For each statement decide keep / downgrade / drop with a reason of at most 20 words.
Checklist — DROP when any applies:
1. The quote is an eligibility / inclusion / exclusion criterion, or a care-setting or site-policy statement (NICU stay, "not routinely prescribed", protocols, guidelines), not an observation about the sampled infants.
2. "healthy infants / newborns / twins" or similar is the only basis for preterm_status=term.
3. The quote uses summary words (predominantly, mostly, most, majority, common, median, mean, average, %) — the value does not hold for every sample in scope.
4. A threshold, minimum, maximum, range or list of timepoints is turned into a single numeric value (age, gestational age, birth weight) or into preterm_status.
5. A subgroup or a single case is applied cohort-wide.
6. Maternal pregnancy-week sampling is read as gestational age at birth; antiretrovirals read as antibiotics; absence of an unrelated illness read as nec_status=no.
7. The paper re-analyses public data and the quote does not clearly describe THIS deposit's cohort.
8. The value is not literally supported by the quote (wrong field, wrong polarity, wrong unit, wrong country).
DOWNGRADE (confidence halved, capped at 0.5) when the statement is plausible but the quote is indirect, ambiguous about scope (which cohort / which samples), or applies_to mapping is inferred.
KEEP when the quote directly and unconditionally states the value for all samples in the stated scope.
Return one verdict per stmt_id; never omit an id."""


def audit_requests(stmts, model, batch=12):
    """stmts: list of dicts with stmt_id, study, pmcid, relation, field, value_normalized, quote, section, applies_to, note, ena_title."""
    reqs, metas = [], []
    for i in range(0, len(stmts), batch):
        b = stmts[i:i + batch]
        lines = []
        for s in b:
            lines.append(json.dumps({k: s.get(k) for k in ("stmt_id", "study", "ena_title", "pmcid", "relation", "field", "value_normalized", "value_raw", "quote", "section", "applies_to", "note", "n_samples_in_scope")}, ensure_ascii=False))
        user = "STATEMENTS:\n" + "\n".join(lines) + "\n\nReturn statement_audit verdicts for every stmt_id."
        reqs.append({"model": model, "system": AUDIT_SYSTEM, "max_tokens": 3000, "tools": [AUDIT_TOOL],
                     "tool_choice": {"type": "tool", "name": "statement_audit"}, "messages": [{"role": "user", "content": user}]})
        metas.append({"ids": [s["stmt_id"] for s in b], "slots": ["audit"]})
    return reqs, metas

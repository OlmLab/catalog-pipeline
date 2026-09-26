"""infant-curation-rules sidecar: validators for the catalog output contract."""
import re

REASON_CODES = ("assay_amplicon", "assay_amplicon_misfiled", "assay_rna", "assay_isolate_genome",
                "assay_other_nonshotgun", "assay_assembly_only", "host_nonhuman", "host_environmental",
                "host_synthetic", "age_adult_only", "age_child_over_36m", "age_maternal_only",
                "age_unknown_no_evidence", "site_excluded", "site_unknown", "fp_salmonella_infantis",
                "fp_bifido_infantis", "fp_name_only", "access_controlled", "access_suppressed",
                "dup_mirror", "dup_reanalysis")
OUTCOMES = ("included", "excluded_deterministic", "excluded_llm", "resolved_from_raw", "predicted",
            "resolved_at_pipeline", "unsure_adjudicated", "sentinel_no_evidence", "validator_rejected")
SOURCE_PREFIXES = ("study.title", "study.abstract", "study.description", "sample.title", "sample.attr.",
                   "run.", "paper.title", "paper.abstract", "paper.fulltext.", "paper.supp.",
                   "sample_id_pattern", "sibling_consensus", "cohort_default", "external_curation.")
ACCESSION_PATTERN = r"\b(PRJ[EDN][A-Z]\d+|SAM[EDN][A-Z]?\d+|[SED]R[RXSPZ]\d{5,}|GS[EM]\d+)\b"
MAX_QUOTE_WORDS = 12
MAX_INFANT_AGE_DAYS = 1100


def validate_reason_code(code):
    """Return (ok, message). None/empty is ok for non-exclusion rows."""
    if code in (None, ""):
        return True, ""
    if code in REASON_CODES:
        return True, ""
    return False, f"reason_code '{code}' not in controlled vocabulary"


def validate_evidence(rows):
    """rows: list of {source, quote}. Checks labeled source prefix and quote length."""
    if not rows:
        return False, "no evidence rows"
    for i, r in enumerate(rows):
        src = str(r.get("source", ""))
        if not any(src.startswith(p) for p in SOURCE_PREFIXES):
            return False, f"evidence[{i}].source '{src}' is not a labeled source"
        q = str(r.get("quote", "")).strip()
        if not q:
            return False, f"evidence[{i}].quote empty"
        if len(q.split()) > MAX_QUOTE_WORDS:
            return False, f"evidence[{i}].quote exceeds {MAX_QUOTE_WORDS} words"
    return True, ""


def age_to_days(value, unit):
    """Deterministic conversion. Returns float days or None if unit unknown."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    u = str(unit).strip().lower()
    factors = {"day": 1, "days": 1, "d": 1, "week": 7, "weeks": 7, "wk": 7, "w": 7,
               "month": 30.4375, "months": 30.4375, "mo": 30.4375, "m": 30.4375,
               "year": 365.25, "years": 365.25, "yr": 365.25, "y": 365.25}
    if u not in factors:
        return None
    return v * factors[u]


def validate_age(value, unit, max_days=None):
    """(ok, message, age_days). In-scope infant sample must be 0..max_days."""
    if max_days is None:
        max_days = MAX_INFANT_AGE_DAYS
    d = age_to_days(value, unit)
    if d is None:
        return False, f"unparseable age {value!r} {unit!r}", None
    if d < 0 or d > max_days:
        return False, f"age {d:.0f} days outside 0-{max_days}", d
    return True, "", d


def find_accessions(text):
    """All archive accessions present in a text blob (the only legitimate source of accessions)."""
    return sorted(set(re.findall(ACCESSION_PATTERN, text or "")))


def validate_accession_seen(accession, sources_text):
    """Rule 4: the accession must literally occur in the material the agent was shown."""
    if not accession:
        return False, "empty accession"
    if accession in find_accessions(sources_text):
        return True, ""
    return False, f"accession {accession} not present in any shown source (Rule 4)"


def sentinel_row(record_id, slot, model, note=None):
    """The explicit no-evidence outcome."""
    return {"record_id": record_id, "slot": slot, "value": None, "outcome": "sentinel_no_evidence",
            "confidence": 0.0, "evidence": [], "model": model, "note": note}


def validate_row(row, sources_text=None):
    """Full contract check. Returns (ok, message). On failure the caller must write
    outcome='validator_rejected' with this message in note."""
    for k in ("record_id", "slot", "outcome", "confidence", "evidence", "model"):
        if k not in row:
            return False, f"missing key {k}"
    if row["outcome"] not in OUTCOMES:
        return False, f"outcome '{row['outcome']}' not allowed"
    if row["outcome"] in ("sentinel_no_evidence", "validator_rejected"):
        return True, ""
    try:
        c = float(row["confidence"])
    except (TypeError, ValueError):
        return False, "confidence not numeric"
    if not 0.0 <= c <= 1.0:
        return False, "confidence outside 0-1"
    if row.get("evidence_limited_to") == "abstract" and c > 0.6:
        return False, "abstract-only evidence requires confidence <= 0.6 (Rule 11)"
    ok, msg = validate_evidence(row["evidence"])
    if not ok:
        return False, msg
    ok, msg = validate_reason_code(row.get("reason_code"))
    if not ok:
        return False, msg
    if row["outcome"].startswith("excluded") and not row.get("reason_code"):
        return False, "exclusion without reason_code"
    if row["slot"] in ("age_at_collection", "age") and row.get("value") is not None:
        ok, msg, _ = validate_age(row["value"], row.get("value_unit"))
        if not ok:
            return False, msg
    if sources_text is not None:
        for acc in find_accessions(str(row.get("value", ""))):
            ok, msg = validate_accession_seen(acc, sources_text)
            if not ok:
                return False, msg
    return True, ""

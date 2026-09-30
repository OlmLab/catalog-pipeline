"""r1_ext.py — route R1 for the four extension fields (health_condition, multiple_birth, sibling_in_study,
geo_subregion). Deterministic maps where the attribute vocabulary is unambiguous; Haiku normalisation of the
distinct free-text values (<=300 per request) for health_condition and geo_subregion; family-identifier
logic for sibling_in_study. Every emitted row is validated with curation_kernel_ext.validate_row.
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
import re, json
import pandas as pd, numpy as np
import scope_constants_ext as SC
import llm_batch_common as LBC

HAIKU = resolve_model("screen")
NULLS = {"", "na", "n/a", "nan", "none", "null", "missing", "not applicable", "not collected", "not provided",
         "unspecified", "unknown", "labcontrol test", "missing: not provided", "not available", "-", "nd", "no data"}


def is_null(v):
    return str(v).strip().lower() in NULLS


def q12(s):
    return " ".join(str(s).split()[:12])


# ------------------------------------------------------------------ deterministic twin maps
TRUE = {"true", "yes", "y", "1", "t"}
FALSE = {"false", "no", "n", "0", "f"}


def det_multiple_birth(key, v):
    """-> (value, confidence, note) or None. Only unambiguous vocabularies."""
    s = str(v).strip(); low = s.lower()
    if key in ("has_twin", "twin_gestation", "is_twin", "twin_gestation_0_no_1_yes", "twin_gestation_0_no_1_yes_1", "maternal_complication_twin"):
        if low in TRUE:
            return "twin", (0.8 if key == "maternal_complication_twin" else 0.9), "boolean_twin"
        if low in FALSE:
            return "singleton", (0.7 if key == "maternal_complication_twin" else 0.85), "boolean_twin_negative"
        return None
    if key == "twin_or_singleton":
        if low.startswith("singleton"): return "singleton", 0.9, "text"
        if low.startswith("twin"): return "twin", 0.9, "text"
        if re.search(r"triplet|quadruplet|multiple", low): return "triplet_or_more", 0.85, "text"
        return None
    if key == "twin_pair":
        if low.startswith("singleton"): return "singleton", 0.9, "text"
        if re.match(r"pair\s*\d+", low): return "twin", 0.85, "pair_code"
        return None
    if key == "twin_id":
        if low in ("not applicable", "na", "n/a"): return "singleton", 0.75, "twin_id_not_applicable"
        if re.fullmatch(r"[ab12]", low): return "twin", 0.85, "twin_id_member"
        return None
    if key == "twin_in_study":
        return ("twin", 0.85, "twin_in_study_true") if low in TRUE else None
    if key == "type_of_twin":
        if re.search(r"gemini|twin|dc/da|mc/da|mc/ma|dz|mz", low): return "twin", 0.85, "twin_type"
        if re.search(r"triplet", low): return "triplet_or_more", 0.85, "twin_type"
        return None
    if key == "twins":
        if re.fullmatch(r"[A-Za-z]{1,4}\d{1,4}\+[A-Za-z]{1,4}\d{1,4}", s): return "twin", 0.85, "pair_code"
        return None
    if key == "host_family_relationship":
        if re.search(r"\btwin\b", low): return "twin", 0.9, "relationship_text"
        if re.search(r"\btriplet\b", low): return "triplet_or_more", 0.9, "relationship_text"
        return None
    return None


# ------------------------------------------------------------------ deterministic geo parsing
GEO_JUNK = re.compile(r"hospital|clinic|university|laborator|centre|center|institute|medical|nicu|ward|\bunit\b|\bdept|department|school of|college", re.I)
URBAN = {"urban", "suburban", "rural", "peri-urban", "periurban", "semi-urban"}


def parse_geo_loc(v):
    """'Country: City' / 'Country:State:City' / 'Country: City, ST' -> candidate sub-national string (unnormalised), or None."""
    s = str(v).strip()
    if is_null(s) or ":" not in s:
        return None
    parts = [p.strip() for p in s.split(":") if p.strip()]
    if len(parts) < 2:
        return None
    sub = parts[1:]
    if len(sub) == 1:
        return sub[0]
    # 'USA:CA:San Diego' -> 'San Diego, CA' ; 'India:Maharashtra,Mumbai' handled by Haiku
    return f"{sub[-1]}, {sub[0]}" if len(sub) == 2 else ", ".join(reversed(sub))


# ------------------------------------------------------------------ Haiku normalisation
COND_SYSTEM = """You normalise per-sample metadata values from infant gut microbiome sequencing deposits into a controlled vocabulary for the field health_condition = the INFANT's clinical status or study group at sampling.
Vocabulary: healthy_control (stated healthy / control / no disease / no symptoms), preterm_nicu (preterm or NICU status given as the condition), nec (necrotizing enterocolitis), sepsis_or_infection (sepsis, bacteraemia, confirmed infection incl. infectious gastroenteritis, TB), ibd_or_gi_disease (IBD, Crohn's, colitis, other GI disease), allergy_or_atopy (asthma, eczema/atopic dermatitis, food allergy, allergic rhinitis), malnutrition (undernutrition, stunting, wasting, growth faltering, SAM/MAM), antibiotic_or_probiotic_trial (the value names a probiotic/antibiotic trial arm and no clinical status), other_disease (a stated disease/abnormality not in the list, or a stated non-healthy status without detail), unknown (uninterpretable codes, missing markers, institution names, values that are not the infant's own status).
Rules: a value that encodes both a clinical status and a trial arm (e.g. 'undernourished_probiotic') -> the clinical status, note the arm. A maternal condition -> unknown. 'Not applicable', 'NA', codes like 'C', 'E', '2', 'OMNI' without a legend -> unknown. Colonisation status (e.g. GBS carriage) is not infection -> unknown. Confidence: 0.9 explicit disease name; 0.7-0.8 control/healthy or negation ('no', 'none', 'not diagnosed'); <=0.6 when inferred from a study-group label. Return every id."""

GEO_SYSTEM = """You normalise sub-national place strings taken from sample geographic-location attributes of human microbiome deposits into 'City, Region' free text.
Output normalized = 'City, Region' when both a city/town and a state/province/region are present, else the single sub-national token as given (city OR region), with standard English spelling and capitalisation (e.g. 'Saint Louis, MO', 'Dhaka', 'Northern Netherlands', 'Sao Paulo'). Keep US state abbreviations as two letters. Drop institution words (hospital, university, medical center) and keep only the place: 'Pittsburgh, Magee-Womens Hospital of UPMC' -> 'Pittsburgh, PA' ONLY if the state is stated; if not stated, 'Pittsburgh'. Never add a city, state or country that is not in the string. Return normalized = '' and kind = 'not_place' when the string is a country only, a whole-country region ('Northern' alone), an urban/rural class, an institution without a place, coordinates, or a missing marker. kind in {city, region, city_region, village, not_place}. confidence 0.9 clear place; 0.7 spelling/abbreviation resolved; <=0.5 unsure. Return every id."""

TOOL_COND = {"name": "normalise_values", "description": "controlled-vocabulary normalisation",
             "input_schema": {"type": "object", "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {
                 "id": {"type": "string"}, "normalized": {"type": "string", "enum": sorted(SC.EXTENSION_VOCAB["health_condition"])},
                 "confidence": {"type": "number"}, "note": {"type": "string"}}, "required": ["id", "normalized", "confidence"]}}}, "required": ["items"]}}
TOOL_GEO = {"name": "normalise_values", "description": "place-name normalisation",
            "input_schema": {"type": "object", "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {
                "id": {"type": "string"}, "normalized": {"type": "string"}, "kind": {"type": "string", "enum": ["city", "region", "city_region", "village", "not_place"]},
                "confidence": {"type": "number"}, "note": {"type": "string"}}, "required": ["id", "normalized", "kind", "confidence"]}}}, "required": ["items"]}}


def haiku_normalise(host, items, system, tool, batch=150, max_concurrency=6):
    """items: list of dict(id, key, value, study). Returns (dict id -> result, tokens)."""
    out, tokens = {}, 0
    pending = list(items)
    for attempt, bsz in enumerate((batch, max(10, batch // 5))):
        if not pending:
            break
        reqs, metas = [], []
        for i in range(0, len(pending), bsz):
            chunk = pending[i:i + bsz]
            body = "\n".join(f"id={it['id']} | attribute={it['key']} | study={it.get('study','')} | value={json.dumps(it['value'])[:200]}" for it in chunk)
            reqs.append({"model": HAIKU, "system": system, "max_tokens": 8000, "temperature": 0, "tools": [tool],
                         "tool_choice": {"type": "tool", "name": "normalise_values"},
                         "messages": [{"role": "user", "content": "Normalise each value. Return every id.\n\n" + body}]})
            metas.append([it["id"] for it in chunk])
        results = host.llm(reqs, max_concurrency=max_concurrency)
        for ids, res in zip(metas, results):
            tokens += LBC.usage_tokens(res)
            parsed = LBC.tool_input(res)
            if not parsed:
                continue
            for it in parsed.get("items", []):
                if str(it.get("id")) in ids:
                    out[str(it["id"])] = it
        pending = [it for it in pending if it["id"] not in out]
        print(f"[haiku] attempt {attempt} done; missing {len(pending)}; tokens {tokens:,}", flush=True)
    return out, tokens


# ------------------------------------------------------------------ row construction
def make_row(sample_key, study, field, raw, norm, conf, key, note, determined_by, scope="sample"):
    return dict(sample_key=sample_key, study_accession=study, field_name=field, field_value=str(raw)[:120], value_normalized=str(norm),
                confidence=float(conf), evidence_source=f"sample.attr.{key}", evidence_locator=key,
                evidence_quote=q12(f"{key}={str(raw)[:80]}"), evidence_limited_to_abstract=0.0, determined_by=determined_by,
                route="R1", scope=scope, parse_note=note, group_audit=None, src_track="ext_r1")


def validate_rows(df, K):
    """Split into (accepted, rejected) with the extended kernel."""
    ok, msgs = [], []
    for r in df.itertuples(index=False):
        row = {"record_id": r.sample_key, "slot": r.field_name, "value": r.value_normalized, "outcome": "resolved_from_raw",
               "confidence": r.confidence, "evidence": [{"source": r.evidence_source, "quote": r.evidence_quote}], "model": r.determined_by}
        good, msg = K.validate_row(row)
        ok.append(good); msgs.append(msg)
    ok = np.array(ok, dtype=bool)
    rej = df[~ok].copy(); rej["reject_reason"] = np.array(msgs, dtype=object)[~ok]
    return df[ok].copy(), rej

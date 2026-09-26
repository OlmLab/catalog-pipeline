"""Blind Sonnet audit of sample determinations (two replicates) and group-scope failure-mode checklist."""
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
import json, re
import pandas as pd
import llm_batch_common as LBC

FIELD_DEF = {
    "age_at_collection_days": "Infant's postnatal age at sample collection, in days (values converted from weeks/months: 1 month = 30.44 d, 1 week = 7 d; 'birth'/'meconium' = 0). Not gestational age, not maternal age, not a timepoint index.",
    "timepoint_label": "The study's own label for the collection timepoint (e.g. 'T1', 'day4', '6M', 'pre-weaning'); a label, not necessarily an age.",
    "sex": "Biological sex of the INFANT whose sample this is: male / female.",
    "preterm_status": "Birth at <37 completed weeks gestation = preterm; >=37 weeks = term. Applies to the infant subject(s) of the sample(s).",
    "delivery_mode": "Mode of birth of the infant: vaginal / c_section (any caesarean) / c_section_elective / c_section_emergency.",
    "antibiotic_exposure": "Whether the INFANT received antibiotics (postnatally, before/at sampling): yes / no. Maternal antibiotics are a different field.",
    "maternal_antibiotics": "Whether the MOTHER received antibiotics during pregnancy, labour/delivery or lactation: yes / no.",
    "feeding_mode": "Infant feeding at collection: exclusive_breast / formula / mixed (breast + formula) / weaned (solid foods introduced).",
    "gestational_age_weeks": "Gestational age at birth in completed weeks (numeric).",
    "birth_weight_grams": "Birth weight in grams (numeric; kg converted x1000).",
    "probiotic_exposure": "Whether the infant received a probiotic supplement: yes / no.",
    "nec_status": "Whether the infant was diagnosed with necrotizing enterocolitis: yes / no.",
    "hmo_supplementation": "Whether the infant received human-milk-oligosaccharide-supplemented formula/supplement: yes / no.",
}
SCOPE_NOTE = {"sample": "This value was assigned to ONE sample from its own record.",
              "group": "This value was assigned to a GROUP of samples (a whole study or a stated subgroup) from study-level text."}


def source_label(row):
    src = str(row.evidence_source)
    loc = str(row.evidence_locator) if isinstance(row.evidence_locator, str) else ""
    if src == "biosample_attr":
        return f"sample.attr.{loc or 'unknown_key'}"
    if src == "run.library_name":
        return "run.library_name"
    if src == "sample.title" and loc == "sample_id_pattern":
        return "sample.title (sample_id_pattern)"
    if src.startswith("paper.supp") and loc:
        return f"{src}[{loc}]"
    return src


def item_text(r):
    return (f"ID {r.audit_id}\n field: {r.field_name} — {FIELD_DEF[r.field_name]}\n stated value: {r.value_normalized}"
            f"\n evidence source: {source_label(r)}\n evidence quote: \"{r.evidence_quote}\"\n {SCOPE_NOTE.get(r.scope, '')}")


AUDIT_TOOL = {"name": "record_verdicts", "description": "Record one verdict per audited item.",
              "input_schema": {"type": "object", "properties": {"items": {"type": "array", "items": {
                  "type": "object", "properties": {"id": {"type": "string"},
                                                   "verdict": {"type": "string", "enum": ["supported", "not_supported", "cannot_tell"]},
                                                   "reason": {"type": "string", "description": "one line, <=25 words"}},
                  "required": ["id", "verdict", "reason"]}}}, "required": ["items"]}}

AUDIT_SYSTEM = ("You are a blind auditor of metadata extractions for an infant gut microbiome catalog. For each item you see ONLY the "
                "field definition, the stated value, the evidence source label and the evidence quote. Judge whether the quote, read "
                "with the source label, supports the stated value for that field. Answer 'supported' if the quote plainly states or "
                "unambiguously implies the value; 'not_supported' if the quote contradicts the value, refers to a different field or "
                "subject (e.g. mother vs infant, gestational vs postnatal age), is a threshold/definition/summary statistic rather than "
                "an observed value, or does not contain the information; 'cannot_tell' if the quote is consistent with the value but "
                "too ambiguous to decide. Give a one-line reason. Do not use outside knowledge about specific studies; unit conversions "
                "and standard abbreviations (CS, VD, F/M, GA, wk, mo) are allowed.")


def make_audit_requests(aud, model, batch=10, max_tokens=1800):
    reqs, metas = [], []
    for i in range(0, len(aud), batch):
        b = aud.iloc[i:i + batch]
        txt = "\n\n".join(item_text(r) for r in b.itertuples())
        reqs.append(dict(prompt=f"Audit the following {len(b)} items. Return exactly one verdict for every ID.\n\n{txt}",
                         system=AUDIT_SYSTEM, model=model, tools=[AUDIT_TOOL],
                         tool_choice={"type": "tool", "name": "record_verdicts"}, max_tokens=max_tokens))
        metas.append({"ids": list(b.audit_id), "slots": ["audit_verdict"]})
    return reqs, metas


def make_rows_factory(aud, slot, model):
    ref = aud.set_index("audit_id")

    def make_rows(meta, parsed, res):
        got = {str(it.get("id", "")).strip(): it for it in (parsed or {}).get("items", []) if isinstance(it, dict)}
        rows = []
        for rid in meta["ids"]:
            r = ref.loc[rid]
            it = got.get(rid)
            if it is None or it.get("verdict") not in ("supported", "not_supported", "cannot_tell"):
                s = LBC.V["sentinel_row"](rid, slot, model, note="missing_id_in_batch")
                rows.append(s)
                continue
            rows.append({"record_id": rid, "slot": slot, "value": it["verdict"], "outcome": "predicted", "confidence": 0.8,
                         "evidence": [{"source": source_label(r), "quote": str(r.evidence_quote)}],
                         "model": model, "note": str(it.get("reason", ""))[:300]})
        return rows
    return make_rows


# ---------------- group-scope failure-mode checklist ----------------
FM = ["threshold_as_value", "summary_statistic_as_value", "subgroup_applied_cohort_wide", "maternal_quote_applied_to_infants"]
GROUP_TOOL = {"name": "record_checklist", "description": "Failure-mode checklist per item.",
              "input_schema": {"type": "object", "properties": {"items": {"type": "array", "items": {
                  "type": "object", "properties": {
                      "id": {"type": "string"},
                      "threshold_as_value": {"type": "boolean", "description": "quote is a definition/inclusion threshold (e.g. '<37 weeks', 'age <1 year') rather than an observed value"},
                      "summary_statistic_as_value": {"type": "boolean", "description": "quote is a mean/median/range/percentage over the cohort applied as if a per-sample value"},
                      "subgroup_applied_cohort_wide": {"type": "boolean", "description": "quote describes only a subgroup (e.g. 'n=12 received antibiotics', 'the CS group') but the value is asserted for the group as a whole"},
                      "maternal_quote_applied_to_infants": {"type": "boolean", "description": "quote is about mothers (maternal antibiotics, maternal age, pregnancy) but value is for an infant field"},
                      "overall": {"type": "string", "enum": ["acceptable", "problematic", "cannot_tell"]},
                      "reason": {"type": "string"}},
                  "required": ["id"] + FM + ["overall", "reason"]}}}, "required": ["items"]}}
GROUP_SYSTEM = ("You audit GROUP-scope metadata values: a value taken from study-level text and applied to a whole study or a stated "
                "subgroup of samples in an infant gut microbiome catalog. For each item, given ONLY the field definition, the stated "
                "value, the source label and the quote, tick each failure mode that applies (true/false) and give an overall call. "
                "'acceptable' means the quote is a plain cohort-wide statement of the value (e.g. 'all infants were born by caesarean "
                "section', 'preterm infants (<32 weeks)' where the study population IS the preterm group). Be literal; do not use outside knowledge.")


def make_group_requests(gaud, model, batch=10, max_tokens=2500):
    reqs, metas = [], []
    for i in range(0, len(gaud), batch):
        b = gaud.iloc[i:i + batch]
        txt = "\n\n".join(item_text(r) for r in b.itertuples())
        reqs.append(dict(prompt=f"Apply the failure-mode checklist to these {len(b)} group-scope items. Return every ID.\n\n{txt}",
                         system=GROUP_SYSTEM, model=model, tools=[GROUP_TOOL],
                         tool_choice={"type": "tool", "name": "record_checklist"}, max_tokens=max_tokens))
        metas.append({"ids": list(b.audit_id), "slots": ["group_checklist"]})
    return reqs, metas


def make_group_rows_factory(gaud, model):
    ref = gaud.set_index("audit_id")

    def make_rows(meta, parsed, res):
        got = {str(it.get("id", "")).strip(): it for it in (parsed or {}).get("items", []) if isinstance(it, dict)}
        rows = []
        for rid in meta["ids"]:
            r = ref.loc[rid]
            it = got.get(rid)
            if it is None or it.get("overall") not in ("acceptable", "problematic", "cannot_tell"):
                rows.append(LBC.V["sentinel_row"](rid, "group_checklist", model, note="missing_id_in_batch"))
                continue
            rows.append({"record_id": rid, "slot": "group_checklist", "value": it["overall"], "outcome": "predicted", "confidence": 0.8,
                         "evidence": [{"source": source_label(r), "quote": str(r.evidence_quote)}], "model": model,
                         "note": str(it.get("reason", ""))[:300], **{k: bool(it.get(k, False)) for k in FM}})
        return rows
    return make_rows

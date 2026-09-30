"""R4: study-level values from abstract + ENA study description only (no OA full text).
Haiku, confidence <= 0.5, evidence_limited_to_abstract=1, evidence_source 'paper.abstract' | 'study.description' | 'study.title'.
Statements are cohort-wide ('all') only; expanded to the study's infant samples like R3.
Driven by a study list; `abstracts` = {study: [(pmid, title, abstract, relation), ...]}.
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
import json, re
import pandas as pd
import llm_batch_common as LBC
from r3_prose_extract import expand, _valid_value, FIELDS

HAIKU = resolve_model("screen")
TOOL = {"name": "study_level_values", "description": "Cohort-wide metadata values evident from abstract/description.",
        "input_schema": {"type": "object", "properties": {"statements": {"type": "array", "items": {"type": "object", "properties": {
            "field": {"type": "string", "enum": [f for f in FIELDS if f != "age_attribute_unit"]},
            "value_normalized": {"type": "string"}, "value_raw": {"type": "string"},
            "source": {"type": "string", "enum": ["paper.abstract", "study.description", "study.title"]},
            "quote": {"type": "string"}, "confidence": {"type": "number"}, "cohort_wide": {"type": "boolean"}, "note": {"type": "string"}},
            "required": ["field", "value_normalized", "source", "quote", "confidence", "cohort_wide"]}}}, "required": ["statements"]}}


def build_request(study, title, desc, papers, system_text):
    ptxt = "\n\n".join(f"PAPER pmid {p[0]} (relation: {p[3]})\nTITLE: {p[1]}\nABSTRACT: {re.sub('<[^>]+>', '', p[2])}" for p in papers) or "(no linked paper abstract)"
    user = f"STUDY {study}\nENA TITLE: {title}\nENA DESCRIPTION: {desc[:3000]}\n\n{ptxt}\n\nReturn study_level_values. Quotes verbatim, <=12 words; cohort_wide=true only if the text says the value holds for all infants."
    return {"model": HAIKU, "system": system_text, "max_tokens": 2000, "tools": [TOOL], "tool_choice": {"type": "tool", "name": "study_level_values"},
            "messages": [{"role": "user", "content": user}]}


def run(studies, descs, abstracts, samples, r1det, host, system_text, out_prefix="r4_pilot", max_concurrency=6):
    LBC.HOST = host
    reqs, metas = [], []
    for s in studies:
        t, d = descs.get(s, ("", ""))
        reqs.append(build_request(s, t, d, abstracts.get(s, []), system_text))
        metas.append({"ids": [s], "slots": ["r4_statements"], "study": s})
    stmts = []

    def make_rows(meta, parsed, res):
        out = []
        for st in parsed.get("statements", []) or []:
            if not isinstance(st, dict):
                continue
            v = str(st.get("value_normalized", "")).strip()
            row = {"record_id": meta["study"], "slot": st.get("field"), "value": v, "value_unit": "days" if st.get("field") == "age_at_collection_days" else None,
                   "outcome": "predicted", "confidence": min(float(st.get("confidence", 0.4)), 0.5), "evidence_limited_to": "abstract", "model": HAIKU,
                   "evidence": [{"source": st.get("source", "paper.abstract"), "quote": str(st.get("quote", ""))}], "note": json.dumps({"cohort_wide": st.get("cohort_wide")})}
            if not _valid_value(st.get("field"), v):
                row["outcome"] = "validator_rejected"; row["note"] = f"validator_rejected: value '{v}' invalid for {st.get('field')}"
            stmts.append(dict(study_accession=meta["study"], field=st.get("field"), value_normalized=v, value_raw=st.get("value_raw"), source=st.get("source"),
                              quote=st.get("quote"), confidence=row["confidence"], cohort_wide=bool(st.get("cohort_wide")), note=st.get("note"), _row=row))
            out.append(row)
        if not out:
            out.append(LBC.V["sentinel_row"](meta["study"], "r4_statements", HAIKU, note="no statements"))
        return out
    _, stats = LBC.run_batches(reqs, metas, make_rows, f"{out_prefix}_statements_log.parquet", HAIKU, max_concurrency=max_concurrency)
    dets = []
    for s in studies:
        ss = []
        for st in stmts:
            if st["study_accession"] != s or not st["cohort_wide"]:
                continue
            ok, _ = LBC.V["validate_row"](st["_row"])
            if ok and st["_row"]["outcome"] == "predicted":
                ss.append({"field": st["field"], "value_normalized": st["value_normalized"], "value_raw": st["value_raw"], "applies_to": {"type": "all"},
                           "quote": st["quote"], "section": "abstract", "confidence": st["confidence"], "_pmcid": st["source"], "_reused": True})
        if ss:
            d = expand(ss, s, samples, r1det)
            if len(d):
                d["confidence"] = d["confidence"].clip(upper=0.5)
                d["evidence_source"] = [st_src for st_src in d["evidence_locator"].str.split("/").str[0]]
                d["evidence_locator"] = "abstract_or_description"
                d["route"] = "R4"; d["determined_by"] = "r4_haiku_abstract"; d["evidence_limited_to_abstract"] = 1
                dets.append(d)
    det = pd.concat(dets, ignore_index=True) if dets else pd.DataFrame()
    stdf = pd.DataFrame([{k: v for k, v in st.items() if k != "_row"} | {"valid": LBC.V["validate_row"](st["_row"])[0] and st["_row"]["outcome"] == "predicted"} for st in stmts])
    return stdf, det, stats

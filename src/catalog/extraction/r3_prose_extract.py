"""R3: group-level statements from open-access full text (JATS via Europe PMC cache), expanded to samples.

Driven by a study list. For each study: pick linked OA papers (own_data first, up to `papers_per_study`),
parse JATS -> abstract + methods (+ results if room), chunk to <= ~12k tokens, ask Sonnet for GROUP-LEVEL
statements {field, value_normalized, applies_to, quote<=12 words, section, confidence}, then expand
deterministically to the study's infant samples:
  all              -> every sample whose body_site_class is primary/unknown and whose title is not maternal
  timepoint_label  -> samples whose R1 timepoint_label (from sample-name parsing) equals the label
  pattern          -> samples whose sample_title/library_name matches the regex
  subgroup         -> recorded only, never expanded
Determinations: evidence_source='paper.fulltext.<section>', scope='group', confidence <= 0.8 (<= 0.6 inferred/reused).
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
import re, json, os
import pandas as pd, numpy as np
from lxml import etree
import llm_batch_common as LBC
from r1_title_parser import parse_sample_name

SONNET = resolve_model("rubric")
FIELDS = ["age_at_collection_days", "delivery_mode", "feeding_mode", "preterm_status", "gestational_age_weeks",
          "birth_weight_grams", "antibiotic_exposure", "maternal_antibiotics", "probiotic_exposure",
          "hmo_supplementation", "nec_status", "country", "age_attribute_unit"]
VOCAB = {"delivery_mode": {"vaginal", "c_section", "c_section_elective", "c_section_emergency"},
         "feeding_mode": {"exclusive_breast", "mixed", "formula", "weaned"}, "preterm_status": {"preterm", "term"},
         "antibiotic_exposure": {"yes", "no"}, "maternal_antibiotics": {"yes", "no"}, "probiotic_exposure": {"yes", "no"},
         "hmo_supplementation": {"yes", "no"}, "nec_status": {"yes", "no"}, "age_attribute_unit": {"days", "weeks", "months", "years"}}
MAX_CHARS = 46000   # ~12k tokens

TOOL = {"name": "cohort_statements", "description": "Group-level metadata statements about the study cohort.",
        "input_schema": {"type": "object", "properties": {"statements": {"type": "array", "items": {"type": "object", "properties": {
            "field": {"type": "string", "enum": FIELDS},
            "value_normalized": {"type": "string"},
            "value_raw": {"type": "string"},
            "applies_to": {"type": "object", "properties": {"type": {"type": "string", "enum": ["all", "timepoint_label", "pattern", "subgroup"]},
                                                            "label": {"type": "string"}, "target": {"type": "string", "enum": ["sample_title", "library_name"]},
                                                            "regex": {"type": "string"}, "description": {"type": "string"}, "inferred": {"type": "boolean"}}, "required": ["type"]},
            "quote": {"type": "string"}, "section": {"type": "string", "enum": ["abstract", "methods", "results", "discussion", "other"]},
            "confidence": {"type": "number"}, "note": {"type": "string"}}, "required": ["field", "value_normalized", "applies_to", "quote", "section", "confidence"]}},
            "cohort_note": {"type": "string"}}, "required": ["statements"]}}


# ------------------------------------------------------------------ JATS
def _text(el):
    return re.sub(r"\s+", " ", " ".join(el.itertext())).strip()


def jats_sections(xml_bytes):
    """Return dict(abstract, methods, results, other) of plain text."""
    try:
        root = etree.fromstring(xml_bytes)
    except Exception:
        try:
            root = etree.fromstring(xml_bytes, parser=etree.XMLParser(recover=True, huge_tree=True))
        except Exception:
            return None
    out = {"abstract": "", "methods": "", "results": "", "other": ""}
    for ab in root.iter("abstract"):
        out["abstract"] += _text(ab) + "\n"
    body = next(root.iter("body"), None)
    if body is None:
        return out
    for sec in body.findall("sec"):
        title = (sec.findtext("title") or "").lower()
        st = (sec.get("sec-type") or "").lower()
        txt = _text(sec)
        if re.search(r"method|material|participant|subject|cohort|study design|population|sample collection|recruit|experimental procedure|star", title + " " + st):
            out["methods"] += txt + "\n"
        elif re.search(r"result", title + " " + st):
            out["results"] += txt + "\n"
        else:
            out["other"] += txt + "\n"
    # nested methods inside 'other' (e.g. Methods after Discussion in Nature format) are caught by title regex above
    return out


def build_chunks(secs, max_chars=MAX_CHARS):
    """Chunk 1: abstract + methods (+ results if room). Extra chunks only for very long methods."""
    head = "ABSTRACT:\n" + secs["abstract"][:6000] + "\n\nMETHODS:\n"
    meth = secs["methods"]
    if not meth.strip():   # fall back to 'other' when section typing failed
        meth = secs["other"]
    chunks = []
    room = max_chars - len(head)
    if len(meth) <= room:
        c = head + meth
        rem = max_chars - len(c) - 200
        if rem > 4000 and secs["results"].strip():
            c += "\n\nRESULTS (truncated):\n" + secs["results"][:rem]
        chunks.append(c)
    else:
        for i in range(0, min(len(meth), 3 * room), room):
            chunks.append(head + meth[i:i + room])
    return chunks


# ------------------------------------------------------------------ context
def study_context(study, samples, r1det, conv, descs, unresolved, attrs_keys):
    smp = samples[samples.study_accession == study]
    titles = smp.sample_title.dropna().unique().tolist()
    libs = smp.library_name.dropna().unique().tolist()
    tl = r1det[(r1det.study_accession == study) & (r1det.field_name == "timepoint_label")].value_normalized.value_counts().head(25)
    cv = conv[conv.study_accession == study][["pattern", "example", "regex", "interpretation"]].to_dict("records")
    ur = [u for u in unresolved if u["study_accession"] == study]
    t, d = descs.get(study, ("", ""))
    return {"study_accession": study, "ena_title": t, "ena_description": d[:1500], "n_samples": int(len(smp)),
            "example_sample_titles": titles[:12], "n_distinct_titles": len(titles), "example_library_names": libs[:12],
            "timepoint_labels_found": {k: int(v) for k, v in tl.items()}, "sample_name_conventions": cv[:8],
            "attribute_keys": sorted(attrs_keys)[:60], "unitless_age_attribute": ur}


def build_request(ctx, relation, pmcid, chunk, system_text):
    user = ("STUDY CONTEXT:\n" + json.dumps(ctx, ensure_ascii=False, indent=0) + f"\n\nPAPER {pmcid} (relation to study: {relation})\n\n" + chunk +
            "\n\nReturn cohort_statements for this study. Quotes verbatim, <=12 words.")
    return {"model": SONNET, "system": system_text, "max_tokens": 4000,
            "tools": [TOOL], "tool_choice": {"type": "tool", "name": "cohort_statements"},
            "messages": [{"role": "user", "content": user}]}


# ------------------------------------------------------------------ expansion
def _valid_value(field, v):
    if field in VOCAB:
        return v in VOCAB[field]
    if field == "age_at_collection_days":
        return re.fullmatch(r"\d+", v) is not None and 0 <= int(v) <= 1100
    if field == "gestational_age_weeks":
        try: return 20 <= float(v) <= 45
        except ValueError: return False
    if field == "birth_weight_grams":
        try: return 300 <= float(v) <= 6000
        except ValueError: return False
    if field == "country":
        return re.fullmatch(r"[A-Z]{2}", v) is not None
    return False


def expand(statements, study, samples, r1det):
    smp = samples[samples.study_accession == study].copy()
    smp = smp[smp.body_site_class.isin(["primary", "unknown"])]
    mother = smp.sample_title.map(lambda t: parse_sample_name(t)["is_mother"]) | smp.library_name.map(lambda t: parse_sample_name(t)["is_mother"])
    smp = smp[~mother]
    tl = r1det[(r1det.study_accession == study) & (r1det.field_name == "timepoint_label")].drop_duplicates("sample_key").set_index("sample_key").value_normalized
    rows = []
    for st in statements:
        a = st.get("applies_to") or {}
        typ = a.get("type")
        if typ == "subgroup" or st["field"] == "age_attribute_unit":
            continue
        if typ == "all":
            targets = smp.sample_key
            inferred = False
        elif typ == "timepoint_label":
            lab = str(a.get("label", "")).strip()
            targets = tl[tl.astype(str).str.strip().str.casefold() == lab.casefold()].index
            targets = smp.sample_key[smp.sample_key.isin(targets)]
            inferred = bool(a.get("inferred"))
        elif typ == "pattern":
            try:
                rx = re.compile(a.get("regex", ""))
            except re.error:
                continue
            col = smp.library_name if a.get("target") == "library_name" else smp.sample_title
            targets = smp.sample_key[col.fillna("").map(lambda x: bool(rx.search(x)))]
            inferred = True
        else:
            continue
        if len(targets) == 0:
            continue
        conf = min(float(st.get("confidence", 0.5)), 0.6 if (inferred or st.get("_reused")) else 0.8)
        for sk in targets:
            rows.append(dict(sample_key=sk, study_accession=study, field_name=st["field"], field_value=st.get("value_raw") or st["value_normalized"],
                             value_normalized=st["value_normalized"], confidence=conf, evidence_source=f"paper.fulltext.{st.get('section','methods')}",
                             evidence_locator=f"{st['_pmcid']}/{st.get('section','methods')}", evidence_quote=" ".join(str(st["quote"]).split()[:12]),
                             determined_by="r3_sonnet_group", route="R3", scope="group", applies_to=json.dumps(a), pmcid=st["_pmcid"],
                             parse_note=("inferred_pattern" if inferred else typ)))
    return pd.DataFrame(rows)


def run(studies, paper_sel, samples, r1det, conv, descs, unresolved, attrs, HL, host, system_text, out_prefix="r3_pilot", papers_per_study=1, max_concurrency=4):
    """paper_sel: DataFrame(study_accession, pmcid, relation) ordered by preference."""
    LBC.HOST = host
    reqs, metas = [], []
    akeys = attrs.merge(samples[["sample_key", "study_accession"]]).groupby("study_accession").attr_key_norm.unique()
    for study in studies:
        pp = paper_sel[paper_sel.study_accession == study].head(papers_per_study)
        if pp.empty:
            continue
        ctx = study_context(study, samples, r1det, conv, descs, unresolved, list(akeys.get(study, [])))
        for p in pp.itertuples(index=False):
            r = HL.epmc_fulltext_xml(p.pmcid)
            if not r.get("ok"):
                continue
            secs = jats_sections(r["body"])
            if not secs:
                continue
            for ci, ch in enumerate(build_chunks(secs)):
                reqs.append(build_request(ctx, p.relation, p.pmcid, ch, system_text))
                metas.append({"ids": [f"{study}|{p.pmcid}|{ci}"], "slots": ["r3_statements"], "study": study, "pmcid": p.pmcid, "relation": p.relation, "chunk": ci, "chars": len(ch)})
    print(f"[r3] {len(reqs)} requests over {len({m['study'] for m in metas})} studies", flush=True)
    all_statements = []

    def make_rows(meta, parsed, res):
        out = []
        sts = parsed.get("statements", [])
        if isinstance(sts, str):
            try: sts = json.loads(sts)
            except Exception: sts = []
        for s in sts:
            if not isinstance(s, dict):
                continue
            s = dict(s); s["_pmcid"] = meta["pmcid"]; s["_study"] = meta["study"]; s["_reused"] = meta["relation"] != "own_data"; s["_chunk"] = meta["chunk"]
            v = str(s.get("value_normalized", "")).strip()
            s["value_normalized"] = v
            ok_v = _valid_value(s.get("field"), v)
            row = {"record_id": meta["study"], "slot": s.get("field"), "value": v, "value_unit": "days" if s.get("field") == "age_at_collection_days" else None,
                   "outcome": "predicted", "confidence": min(float(s.get("confidence", 0.5)), 0.8), "model": SONNET,
                   "evidence": [{"source": f"paper.fulltext.{s.get('section','methods')}", "quote": str(s.get("quote", ""))}],
                   "note": json.dumps(s.get("applies_to"))}
            if not ok_v:
                row["outcome"] = "validator_rejected"; row["note"] = f"validator_rejected: value '{v}' not in vocabulary for {s.get('field')}"
            s["_row"] = row
            all_statements.append(s)
            out.append(row)
        if not out:
            out.append(LBC.V["sentinel_row"](meta["study"], "r3_statements", SONNET, note=f"no statements {meta['pmcid']} chunk {meta['chunk']}"))
        return out
    logdf, stats = LBC.run_batches(reqs, metas, make_rows, f"{out_prefix}_statements_log.parquet", SONNET, max_concurrency=max_concurrency)
    # keep only validator-passing statements (row validated in run_batches -> outcome stays 'predicted')
    st_rows = []
    for s in all_statements:
        ok, msg = LBC.V["validate_row"](s["_row"])
        ok = ok and s["_row"]["outcome"] == "predicted"
        st_rows.append(dict(study_accession=s["_study"], pmcid=s["_pmcid"], reused=s["_reused"], chunk=s["_chunk"], field=s.get("field"), value_normalized=s["value_normalized"],
                            value_raw=s.get("value_raw"), applies_to=json.dumps(s.get("applies_to")), quote=s.get("quote"), section=s.get("section"),
                            confidence=s.get("confidence"), note=s.get("note"), valid=ok, reject_msg=None if ok else (msg or s["_row"].get("note"))))
    stdf = pd.DataFrame(st_rows)
    dets = []
    for study in studies:
        ss = [s for s in all_statements if s["_study"] == study and LBC.V["validate_row"](s["_row"])[0] and s["_row"]["outcome"] == "predicted"]
        if ss:
            d = expand(ss, study, samples, r1det)
            if len(d):
                dets.append(d)
    det = pd.concat(dets, ignore_index=True) if dets else pd.DataFrame()
    stats["studies"] = len({m["study"] for m in metas}); stats["papers"] = len({(m["study"], m["pmcid"]) for m in metas})
    return stdf, det, stats, metas

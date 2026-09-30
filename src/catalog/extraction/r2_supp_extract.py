"""R2: per-sample determinations from supplementary tables of papers linked to a study.

Driven by a study list. Pipeline per (study, table):
  1. table candidates = supp_inventory rows (has_sample_id_final) whose pmcid is linked to the study
  2. read the whole table (col_reader.read_rows from the cached EPMC supplementary ZIP)
  3. ID mapping: try sid_col first, then every other column; keys = study's own sample/secondary/run/
     experiment accessions, library_name, sample_title, subject_id_raw; methods exact -> casefold ->
     alnum -> leading-zero-stripped digit groups -> common prefix/suffix stripped -> token (>=4 chars,
     unique). A table counts only if >=50% of its non-empty IDs map to THIS study (and >=3 matches).
  4. Haiku classifies columns -> target fields (<=15 tables per request), with a coding legend for
     coded values; deterministic normalisation (r1_parsers) with the legend as fallback.
  5. Emit rows: evidence_source='paper.supp.table', evidence_locator='<pmcid>/<file>/<sheet>!<col>:<row>',
     evidence_quote='<header>=<cell>'. Subject-level tables (mapped via subject id) only propagate
     static fields (delivery, preterm, GA, birth weight, sex, country, maternal_antibiotics).
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
import os, re, io, json, zipfile, math
import pandas as pd, numpy as np
import col_reader as CR, supp_parse as SP, r1_parsers as RP
import llm_batch_common as LBC

HAIKU = resolve_model("screen")
FIELDS = ["age_at_collection_days", "delivery_mode", "feeding_mode", "preterm_status", "gestational_age_weeks",
          "birth_weight_grams", "antibiotic_exposure", "maternal_antibiotics", "probiotic_exposure",
          "hmo_supplementation", "nec_status", "country", "sex", "subject_id", "timepoint_label"]
STATIC = {"delivery_mode", "preterm_status", "gestational_age_weeks", "birth_weight_grams", "sex", "country", "maternal_antibiotics", "subject_id"}
VOCAB = {"delivery_mode": {"vaginal", "c_section", "c_section_elective", "c_section_emergency"},
         "feeding_mode": {"exclusive_breast", "mixed", "formula", "weaned"},
         "preterm_status": {"preterm", "term"}, "sex": {"male", "female"}}
YESNO = {"antibiotic_exposure", "maternal_antibiotics", "probiotic_exposure", "hmo_supplementation", "nec_status"}
ZIP_DIR = "supp_zips"


# ------------------------------------------------------------------ ID normalisation
def _n_case(s): return str(s).strip().casefold()
def _n_alnum(s): return re.sub(r"[^a-z0-9]", "", _n_case(s))
def _n_lz(s): return re.sub(r"(?<![0-9])0+(?=[0-9])", "", _n_alnum(s))
NORMS = [("exact", lambda s: str(s).strip()), ("casefold", _n_case), ("alnum", _n_alnum), ("alnum_lz", _n_lz)]


def study_keys(study, samples, runs):
    """dict: norm_level -> {norm_id: (sample_key, kind)}; kinds: sample|run|library|title|subject."""
    smp = samples[samples.study_accession == study]
    rn = runs[runs.study_accession == study]
    pairs = []
    for c, kind in (("sample_key", "sample"), ("secondary_sample", "sample"), ("library_name", "library"), ("sample_title", "title"), ("subject_id_raw", "subject")):
        if c in smp:
            pairs += [(v, k, kind) for v, k in zip(smp[c], smp.sample_key) if isinstance(v, str) and v.strip()]
    for c, kind in (("run_accession", "run"), ("experiment_accession", "run"), ("secondary_sample_accession", "sample"), ("sample_accession", "sample"), ("library_name", "library")):
        if c in rn:
            m = rn.dropna(subset=[c])
            # map run rows to sample_key via sample_accession (SAMN/SAMEA) or secondary
            sec2key = dict(zip(smp.secondary_sample, smp.sample_key))
            skset = set(smp.sample_key)
            sk = [a if a in skset else sec2key.get(b) for a, b in zip(m.sample_accession, m.secondary_sample_accession)]
            pairs += [(v, k, kind) for v, k in zip(m[c], sk) if isinstance(v, str) and isinstance(k, str)]
    # generic values (shared by >1 DISTINCT sample) are useless as keys. Count distinct sample_keys per value, not
    # occurrences: a sample with several runs repeats its accession/library once per run row and was wrongly dropped.
    uniq = {}
    for v, k, kind in pairs:
        uniq.setdefault(v, set()).add(k)
    pairs = list(dict.fromkeys((v, k, kind) for v, k, kind in pairs if len(uniq[v]) == 1 or kind == "subject"))
    levels = {}
    for name, fn in NORMS:
        d = {}
        for v, k, kind in pairs:
            nv = fn(v)
            if not nv:
                continue
            if nv in d and d[nv][0] != k and kind != "subject":
                d[nv] = (None, "ambiguous")
            elif kind == "subject":
                d.setdefault(nv, ([], "subject"))
                if isinstance(d[nv][0], list):
                    d[nv][0].append(k)
            else:
                d.setdefault(nv, (k, kind))
        levels[name] = d
    # token index (>=4 chars) from library/title split on separators, unique only
    tok = {}
    for v, k, kind in pairs:
        if kind in ("library", "title", "sample"):
            for t in re.split(r"[._\-\s/|:]+", str(v)):
                t2 = _n_alnum(t)
                if len(t2) >= 4:
                    tok.setdefault(t2, set()).add(k)
    levels["token"] = {t: (next(iter(s)), "token") for t, s in tok.items() if len(s) == 1}
    return levels


def _strip_affix(ids):
    """common prefix/suffix across the table's ids (only if it leaves >=2 chars)."""
    s = [str(i) for i in ids if i]
    if len(s) < 3:
        return ids
    pre = os.path.commonprefix(s)
    suf = os.path.commonprefix([x[::-1] for x in s])[::-1]
    out = []
    for x in ids:
        y = str(x)
        if pre and y.startswith(pre) and len(y) - len(pre) >= 2:
            y = y[len(pre):]
        if suf and y.endswith(suf) and len(y) - len(suf) >= 2:
            y = y[:-len(suf)]
        out.append(y)
    return out


def map_ids(ids, levels):
    """Return (method, {row_index: sample_key or [sample_keys]}, rate, n_nonempty)."""
    clean = [None if (v is None or str(v).strip() == "" or str(v).strip().lower() in ("nan", "na", "none")) else str(v).strip() for v in ids]
    nz = [i for i, v in enumerate(clean) if v]
    if len(nz) < 3:
        return None, {}, 0.0, len(nz)
    best = (None, {}, 0.0)
    variants = [("", clean), ("affix_", _strip_affix(clean))]
    for vname, vals in variants:
        for name, fn in NORMS + [("token", _n_alnum)]:
            d = levels[name]
            hits, kind = {}, ""
            for i in nz:
                nv = fn(vals[i])
                if nv in d and d[nv][0] is not None:
                    hits[i] = d[nv][0]
                    kind = d[nv][1]
            rate = len(hits) / len(nz)
            if rate > best[2]:
                best = (vname + name + ":" + kind, hits, rate)
            if rate >= 0.95:
                return best[0], best[1], best[2], len(nz)
    return best[0], best[1], best[2], len(nz)


# ------------------------------------------------------------------ table reading
def zip_path(pmcid, HL):
    os.makedirs(ZIP_DIR, exist_ok=True)
    p = os.path.join(ZIP_DIR, f"{pmcid}.zip")
    if not os.path.exists(p):
        r = HL.epmc_supplementary_zip(pmcid)
        if not r.get("ok"):
            return None
        open(p, "wb").write(r["body"])
    return p


def read_table(zp, member, sheet, header_row_index):
    try:
        rows = CR.read_rows(zp, member, sheet)
    except Exception as e:
        return None, None, f"read_error:{type(e).__name__}"
    if not rows or header_row_index >= len(rows):
        return None, None, "empty"
    hdr = [SP._clean(c) if c is not None else "" for c in rows[header_row_index]]
    hdr = [h if h else f"col{i}" for i, h in enumerate(hdr)]
    body = [[SP._clean(c) if c is not None else None for c in r] + [None] * (len(hdr) - len(r)) for r in rows[header_row_index + 1:]]
    body = [r for r in body if any(c not in (None, "") for c in r)]
    return hdr, body, None


# ------------------------------------------------------------------ Haiku column classification
CLASSIFY_SYSTEM = open(_prompt_path("r2_column_classify_system.txt")).read() if os.path.exists(_prompt_path("r2_column_classify_system.txt")) else None

TOOL = {"name": "classify_tables", "description": "Map supplementary-table columns to infant-metadata fields.",
        "input_schema": {"type": "object", "properties": {"tables": {"type": "array", "items": {"type": "object", "properties": {
            "table_id": {"type": "string"},
            "columns": {"type": "array", "items": {"type": "object", "properties": {
                "header": {"type": "string"},
                "field": {"type": "string", "enum": FIELDS + ["none"]},
                "unit": {"type": "string", "enum": ["days", "weeks", "months", "years", "grams", "kg", "none"]},
                "legend": {"type": "array", "items": {"type": "object", "properties": {"raw": {"type": "string"}, "normalized": {"type": "string"}}, "required": ["raw", "normalized"]}},
                "note": {"type": "string"}}, "required": ["header", "field"]}}}, "required": ["table_id", "columns"]}}}, "required": ["tables"]}}


def build_classify_request(tables, system_text):
    """tables: list of dict(table_id, headers, sample_rows, sid_header, context)."""
    parts = []
    for t in tables:
        parts.append(f"TABLE {t['table_id']}\nfile: {t['file']} sheet: {t['sheet']}\nsample-id column: {t['sid_header']}\nheaders: {json.dumps(t['headers'])[:1500]}\nexample rows: {json.dumps(t['sample_rows'])[:2500]}\ndistinct values per column (up to 8): {json.dumps(t['distinct'])[:2500]}\n")
    return {"model": HAIKU, "system": system_text, "max_tokens": 6000, "temperature": 0,
            "tools": [TOOL], "tool_choice": {"type": "tool", "name": "classify_tables"},
            "messages": [{"role": "user", "content": "Classify the columns of each table. Only list columns that carry one of the fields; omit 'none' columns.\n\n" + "\n".join(parts)}]}


# ------------------------------------------------------------------ value normalisation
def normalize(field, raw, unit, legend, header):
    s = "" if raw is None else str(raw).strip()
    if RP.is_null(s):
        return None, "null"
    low = s.lower()
    if field == "feeding_mode" and (low in RP.YES or low in RP.NO or low in ("y", "n", "true", "false", "0", "1")):
        return None, "boolean_feeding_column"   # F2 precedes legends
    if legend and low in legend:
        return legend[low], "legend"
    if field == "age_at_collection_days":
        # F1 (pilot): age groups / ranges ("0 - 1 month", "6 months-1 yr", "12-24 months") are never a value
        if re.search(r"\d[^\d]{0,12}(?:-|–|to)\s*\d|\bgroup\b|<|>|≤|≥", low):
            return None, "range_or_group"
        u = unit if unit in ("days", "weeks", "months", "years") else CR.unit_from_header(header)
        d = CR.parse_age_value(s, u, LBC.V["age_to_days"])
        if d is None:
            d2, note = RP.parse_age_text(s)
            if note.startswith("range"):
                return None, "range_or_group"
            return (str(int(round(d2))), note) if d2 is not None else (None, "unparsed")
        return str(int(round(d))), f"age {u or 'embedded'}"
    if field == "gestational_age_weeks":
        v, note = RP.parse_ga(s, unit if unit in ("weeks", "days") else "weeks")
        return (None if v is None else str(v)), note
    if field == "birth_weight_grams":
        if unit == "kg" and re.fullmatch(RP.NUM, s):
            return str(int(round(float(s) * 1000))), "kg"
        v, note = RP.parse_bw(s)
        return (None if v is None else str(v)), note
    if field == "delivery_mode":
        return RP.parse_delivery(s)
    if field == "feeding_mode":
        # F2 (pilot): boolean breastfeeding / solids columns (is_bf=yes, started_solids=yes, breastfed=no) do not fix feeding_mode
        if low in RP.YES or low in RP.NO or low in ("y", "n", "true", "false", "0", "1"):
            return None, "boolean_feeding_column"
        v, n = RP.parse_feeding(s)
        return ("weaned" if v == "weaned/solids" else v), n
    if field == "preterm_status":
        if re.search(r"pre-?term|prematur", low): return "preterm", "text"
        if re.search(r"\bterm\b|full", low): return "term", "text"
        if re.fullmatch(RP.NUM, s):   # GA in weeks
            x = float(s)
            if 22 <= x <= 44: return ("preterm" if x < 37 else "term"), "from_ga"
        return RP.parse_yesno(s)[0] and ({"yes": "preterm", "no": "term"}[RP.parse_yesno(s)[0]], "yesno") or (None, "unparsed")
    if field == "nec_status":
        return RP.parse_nec(s)
    if field in YESNO:
        v, n = RP.parse_yesno(s, "antibiotic" if "antibiotic" in field else "")
        if v is None and re.fullmatch(RP.NUM, s):
            v, n = ("yes" if float(s) > 0 else "no"), "numeric_count"
        return v, n
    if field == "sex":
        return RP.parse_sex(s)
    if field == "country":
        return RP.parse_country(s)
    if field in ("subject_id", "timepoint_label"):
        return s[:60], "label"
    return None, "no_field"


# ------------------------------------------------------------------ main
POOLED_MIN = 20   # exact accession matches in a pooled (multi-study) table: cannot be false positives


def gate(studies, worklist, samples, runs, HL):
    """Stage 1: read tables, map IDs, apply the >=50% gate (plus the exact-accession pooled gate)."""
    keys_cache, mapping_rows, tables_ok, read_cache = {}, [], [], {}
    wl = worklist[worklist.study_accession.isin(set(studies))].drop_duplicates(["pmcid", "file", "sheet", "study_accession"])
    for i, t in enumerate(wl.itertuples(index=False)):
        st = t.study_accession
        if st not in keys_cache:
            keys_cache[st] = study_keys(st, samples, runs)
        zp = zip_path(t.pmcid, HL)
        rec = dict(study_accession=st, pmcid=t.pmcid, paper_id=t.paper_id, relation=t.relation, file=t.file, sheet=t.sheet, n_rows=None, id_col=None, method=None, n_ids=0, n_mapped=0, rate=0.0, status=None)
        if zp is None:
            rec["status"] = "zip_missing"; mapping_rows.append(rec); continue
        ck = (t.pmcid, t.file, t.sheet)
        if ck not in read_cache:
            read_cache[ck] = read_table(zp, t.file, t.sheet, int(t.header_row_index or 0))
        hdr, body, err = read_cache[ck]
        if err:
            rec["status"] = err; mapping_rows.append(rec); continue
        rec["n_rows"] = len(body)
        if len(body) > 60000:
            rec["status"] = "too_large"; mapping_rows.append(rec); continue
        order = []
        if isinstance(t.sid_col, str) and t.sid_col in hdr:
            order.append(hdr.index(t.sid_col))
        order += [j for j in range(len(hdr)) if j not in order]
        best = (None, None, {}, 0.0, 0)
        for j in order[:40]:
            col = [r[j] if j < len(r) else None for r in body]
            method, hits, rate, n = map_ids(col, keys_cache[st])
            if rate > best[3]:
                best = (j, method, hits, rate, n)
            if rate >= 0.95:
                break
        j, method, hits, rate, n = best
        rec.update(id_col=hdr[j] if j is not None else None, method=method, n_ids=n, n_mapped=len(hits), rate=round(rate, 3))
        exact_acc = bool(method) and method.split(":")[0].endswith("exact") and method.endswith((":run", ":sample"))
        if rate >= 0.5 and len(hits) >= 3:
            rec["status"] = "mapped"
        elif exact_acc and len(hits) >= POOLED_MIN:
            rec["status"] = "mapped_pooled"
        else:
            rec["status"] = "below_gate" if len(hits) else "no_match"
        mapping_rows.append(rec)
        if rec["status"].startswith("mapped"):
            tables_ok.append(dict(table_id=f"T{len(tables_ok)}", study_accession=st, pmcid=t.pmcid, paper_id=t.paper_id, file=t.file, sheet=t.sheet, hdr=hdr, body=body, id_col=j, hits=hits, method=method, sid_header=hdr[j], pooled=rec["status"] == "mapped_pooled"))
    return pd.DataFrame(mapping_rows), tables_ok


def run(studies, worklist, samples, runs, HL, host, out_prefix="r2_pilot", system_text=None, batch=15, max_concurrency=6, gated=None):
    LBC.HOST = host
    mapdf, tables_ok = gated if gated is not None else gate(studies, worklist, samples, runs, HL)
    print(f"[r2] tables read {len(mapdf)}, mapped {len(tables_ok)}", flush=True)
    if not tables_ok:
        return pd.DataFrame(), mapdf, {"requests": 0, "tokens": 0}
    # ---- Haiku classification
    reqs, metas = [], []
    for b in range(0, len(tables_ok), batch):
        chunk = tables_ok[b:b + batch]
        tabs = []
        for tb in chunk:
            hdr, body = tb["hdr"], tb["body"]
            distinct = {}
            for j, h in enumerate(hdr[:80]):
                vals = pd.Series([r[j] for r in body[:2000] if j < len(r) and r[j] not in (None, "")]).astype(str)
                u = vals.drop_duplicates().head(8).tolist()
                if u:
                    distinct[h] = u
            tabs.append(dict(table_id=tb["table_id"], file=tb["file"], sheet=tb["sheet"], sid_header=tb["sid_header"], headers=hdr[:80], sample_rows=[r[:80] for r in body[:3]], distinct=distinct))
        reqs.append(build_classify_request(tabs, system_text))
        metas.append({"ids": [tb["table_id"] for tb in chunk], "slots": ["r2_classify"]})
    classified = {}

    def make_rows(meta, parsed, res):
        out = []
        for tb in parsed.get("tables", []):
            classified[tb.get("table_id")] = tb.get("columns", [])
            out.append({"record_id": tb.get("table_id"), "slot": "r2_classify", "value": json.dumps(tb.get("columns", []))[:2000], "outcome": "predicted",
                        "confidence": 0.7, "evidence": [{"source": "paper.supp.table", "quote": "column headers"}], "model": HAIKU})
        for rid in meta["ids"]:
            if rid not in classified:
                out.append(LBC.V["sentinel_row"](rid, "r2_classify", HAIKU, note="missing_from_batch"))
        return out
    _, stats = LBC.run_batches(reqs, metas, make_rows, f"{out_prefix}_classify_log.parquet", HAIKU, max_concurrency=max_concurrency)
    # re-run missing at batch 5
    missing = [tb for tb in tables_ok if tb["table_id"] not in classified]
    if missing:
        reqs2, metas2 = [], []
        for b in range(0, len(missing), 5):
            chunk = missing[b:b + 5]
            tabs = [dict(table_id=tb["table_id"], file=tb["file"], sheet=tb["sheet"], sid_header=tb["sid_header"], headers=tb["hdr"][:60], sample_rows=[r[:60] for r in tb["body"][:3]], distinct={}) for tb in chunk]
            r = build_classify_request(tabs, system_text); r["max_tokens"] = 8000
            reqs2.append(r); metas2.append({"ids": [tb["table_id"] for tb in chunk], "slots": ["r2_classify"]})
        _, st2 = LBC.run_batches(reqs2, metas2, make_rows, f"{out_prefix}_classify_log2.parquet", HAIKU, max_concurrency=max_concurrency)
        stats["tokens"] += st2["tokens"]; stats["requests"] += st2["requests"]
    json.dump({tb["table_id"]: dict(study=tb["study_accession"], pmcid=tb["pmcid"], file=tb["file"], sheet=tb["sheet"], columns=classified.get(tb["table_id"], [])) for tb in tables_ok}, open(f"{out_prefix}_classified_columns.json", "w"))
    rel = worklist.drop_duplicates(["pmcid", "study_accession"]).set_index(["pmcid", "study_accession"]).relation.to_dict()
    det_all = extract(tables_ok, classified, rel)
    det = select_best(det_all)
    return det, mapdf, stats, det_all


def extract(tables_ok, classified, relation_lookup=None):
    """Stage 3: deterministic extraction of classified columns for mapped rows. relation_lookup: {(pmcid, study): relation}."""
    rows = []
    for tb in tables_ok:
        cols = classified.get(tb["table_id"], [])
        hdr, body = tb["hdr"], tb["body"]
        subject_level = ":subject" in (tb["method"] or "")
        for c in cols:
            f = c.get("field")
            if f not in FIELDS or f == "none":
                continue
            if c.get("header") not in hdr:
                continue
            if subject_level and f not in STATIC:
                continue
            j = hdr.index(c["header"])
            if j == tb["id_col"] and f not in ("subject_id", "timepoint_label"):
                continue
            legend = {str(l.get("raw", "")).strip().lower(): l.get("normalized") for l in (c.get("legend") or []) if l.get("normalized") in VOCAB.get(f, {"yes", "no"}) or f in ("age_at_collection_days",)}
            legend = {k: v for k, v in legend.items() if f not in ("age_at_collection_days",)}  # legends only for categorical
            unit = c.get("unit") if c.get("unit") not in (None, "none") else None
            for ri, sk in tb["hits"].items():
                raw = body[ri][j] if j < len(body[ri]) else None
                val, note = normalize(f, raw, unit, legend, c["header"])
                if val is None:
                    continue
                if f == "age_at_collection_days" and not (0 <= float(val) <= 1100):
                    continue
                if f == "gestational_age_weeks" and not (20 <= float(val) <= 45):
                    continue
                targets = sk if isinstance(sk, list) else [sk]
                for tk in targets:
                    rows.append(dict(sample_key=tk, study_accession=tb["study_accession"], field_name=f, field_value=str(raw)[:120], value_normalized=str(val),
                                     confidence=(0.85 if not subject_level else 0.75) - (0.1 if tb.get("pooled") else 0.0), evidence_source="paper.supp.table",
                                     evidence_locator=f"{tb['pmcid']}/{tb['file']}/{tb['sheet']}!{c['header']}:{ri + 1}",
                                     evidence_quote=f"{c['header']}={str(raw)[:60]}", determined_by=f"r2_haiku_cols+det_norm", route="R2",
                                     parse_note=f"{note}; map={tb['method']}{'; pooled' if tb.get('pooled') else ''}", pmcid=tb["pmcid"], paper_id=tb["paper_id"]))
    det = pd.DataFrame(rows)
    if len(det) and relation_lookup is not None:
        det["relation"] = [relation_lookup.get((a, b)) for a, b in zip(det.pmcid, det.study_accession)]
        det["pooled"] = det.parse_note.str.contains("pooled")
    # validator pass on a row-contract projection
    if len(det):
        ok = []
        for r in det.itertuples(index=False):
            row = {"record_id": r.sample_key, "slot": r.field_name, "value": r.value_normalized, "value_unit": "days" if r.field_name == "age_at_collection_days" else None,
                   "outcome": "resolved_from_raw", "confidence": r.confidence, "evidence": [{"source": "paper.supp.table", "quote": " ".join(r.evidence_quote.split()[:12])}], "model": "deterministic+" + HAIKU}
            ok.append(LBC.V["validate_row"](row)[0])
        det = det[np.array(ok)]
    return det


TABLE_RANK = {(True, False): 0, (True, True): 1, (False, False): 2, (False, True): 3}   # (own_data, pooled)


def select_best(det):
    """F3 (pilot): one source table per study x field, ranked own_data>reused and non-pooled>pooled, then coverage;
    per sample take the value from the best-ranked table that has one (no majority vote across tables with different semantics)."""
    if not len(det):
        return det
    d = det.copy()
    d["_tab"] = d.pmcid + "/" + d.evidence_locator.str.split("!").str[0]
    d["_rank"] = [TABLE_RANK[(r == "own_data", bool(p))] for r, p in zip(d.relation, d.pooled)]
    cov = d.groupby(["study_accession", "field_name", "_tab"]).sample_key.nunique().rename("_cov").reset_index()
    d = d.merge(cov, on=["study_accession", "field_name", "_tab"])
    nv = d.groupby(["sample_key", "field_name"]).value_normalized.nunique().rename("n_values_in_route").reset_index()
    # reused pooled tables (rank 3) are independent re-curations of the same deposit: use a majority vote among them
    pooled = d[d._rank == 3]
    if len(pooled):
        maj = pooled.groupby(["sample_key", "field_name", "value_normalized"]).size().rename("_votes").reset_index()
        d = d.merge(maj, on=["sample_key", "field_name", "value_normalized"], how="left")
        d["_votes"] = d["_votes"].fillna(0)
    else:
        d["_votes"] = 0
    d = d.sort_values(["sample_key", "field_name", "_rank", "_votes", "_cov", "confidence"], ascending=[True, True, True, False, False, False])
    best = d.drop_duplicates(["sample_key", "field_name"]).drop(columns=["_tab", "_rank", "_cov", "_votes"])
    return best.merge(nv, on=["sample_key", "field_name"], how="left")

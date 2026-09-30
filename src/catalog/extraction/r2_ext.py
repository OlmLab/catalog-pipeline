"""r2_ext.py — route R2 for the four extension fields over tables ALREADY accepted in sample_determinations.
Row->sample mapping is taken from the accepted rows' evidence_locator (<pmcid>/<file>/<sheet>!<col>:<row>), so no
new ID gate is run. Haiku re-classifies columns with r2_column_classify_system_ext.txt; only the four extension
fields are extracted; values are normalised deterministically (multiple_birth, sibling_in_study legends) or via the
R1 Haiku normalisers (health_condition, geo_subregion) with the same evidence-fidelity checks.
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
import os, re, json
import pandas as pd, numpy as np
import r2_supp_extract_v2 as R2
import r1_ext as RX
import llm_batch_common as LBC

HAIKU = R2.HAIKU
EXT_FIELDS = ["health_condition", "multiple_birth", "sibling_in_study", "geo_subregion"]
ALL_FIELDS = R2.FIELDS + EXT_FIELDS
STATIC_EXT = {"multiple_birth", "sibling_in_study", "geo_subregion"}   # propagate through subject-level joins
TOOL = json.loads(json.dumps(R2.TOOL))
TOOL["input_schema"]["properties"]["tables"]["items"]["properties"]["columns"]["items"]["properties"]["field"]["enum"] = ALL_FIELDS + ["none"]
SYSTEM = open(_prompt_path("r2_column_classify_system_ext.txt")).read()


def build_request(tabs):
    r = R2.build_classify_request(tabs, SYSTEM)
    r["tools"] = [TOOL]
    return r


def table_payload(tb, max_cols=80):
    hdr, body = tb["hdr"], tb["body"]
    distinct = {}
    for j, h in enumerate(hdr[:max_cols]):
        vals = pd.Series([r[j] for r in body[:2000] if j < len(r) and r[j] not in (None, "")]).astype(str)
        u = vals.drop_duplicates().head(8).tolist()
        if u:
            distinct[h] = u
    return dict(table_id=tb["table_id"], file=tb["file"], sheet=tb["sheet"], sid_header=tb["sid_header"], headers=hdr[:max_cols],
                sample_rows=[r[:max_cols] for r in body[:3]], distinct=distinct)


def classify(host, tables_ok, batch=12, max_concurrency=6):
    """-> (classified: table_id -> columns, tokens)."""
    classified, tokens = {}, 0
    pending = list(tables_ok)
    for attempt, bsz in enumerate((batch, 4)):
        if not pending:
            break
        reqs, metas = [], []
        for i in range(0, len(pending), bsz):
            chunk = pending[i:i + bsz]
            reqs.append(build_request([table_payload(tb) for tb in chunk]))
            metas.append([tb["table_id"] for tb in chunk])
        results = host.llm(reqs, max_concurrency=max_concurrency)
        for ids, res in zip(metas, results):
            tokens += LBC.usage_tokens(res)
            parsed = LBC.tool_input(res)
            if not parsed:
                continue
            for tb in parsed.get("tables", []):
                if tb.get("table_id") in ids:
                    classified[tb["table_id"]] = tb.get("columns", [])
        pending = [tb for tb in pending if tb["table_id"] not in classified]
        print(f"[classify] attempt {attempt}: classified {len(classified)}, missing {len(pending)}, tokens {tokens:,}", flush=True)
    return classified, tokens


# ------------------------------------------------------------------ deterministic normalisers
def norm_multiple_birth(raw, legend):
    low = str(raw).strip().lower()
    if RX.is_null(low): return None, "null"
    if legend and low in legend: return legend[low], "legend"
    if re.search(r"triplet|quadruplet|multiple", low): return "triplet_or_more", "text"
    if re.search(r"\btwins?\b|\bmz\b|\bdz\b|monozyg|dizyg", low): return "twin", "text"
    if re.search(r"singleton", low): return "singleton", "text"
    return None, "unparsed"


def norm_sibling(raw, legend):
    low = str(raw).strip().lower()
    if RX.is_null(low): return None, "null"
    if legend and low in legend: return legend[low], "legend"
    if low in RX.TRUE - {"1"}: return "yes", "boolean"
    if low in RX.FALSE - {"0"}: return "no", "boolean"
    return None, "unparsed"


def extract(tables_ok, classified, cond_lookup, geo_lookup):
    """cond_lookup: (header, raw) -> (value, conf, note) ; geo_lookup: (header, raw) -> (value, conf, note)."""
    rows = []
    for tb in tables_ok:
        cols = classified.get(tb["table_id"], [])
        hdr, body = tb["hdr"], tb["body"]
        for c in cols:
            f = c.get("field")
            if f not in EXT_FIELDS or c.get("header") not in hdr:
                continue
            if tb["subject_level"] and f not in STATIC_EXT:
                continue
            j = hdr.index(c["header"])
            if j == tb["id_col"]:
                continue
            vocab = {"multiple_birth": {"singleton", "twin", "triplet_or_more"}, "sibling_in_study": {"yes", "no"},
                     "health_condition": set(RX.SC.EXTENSION_VOCAB["health_condition"]) - {"unknown"}}.get(f, set())
            legend = {str(l.get("raw", "")).strip().lower(): l.get("normalized") for l in (c.get("legend") or []) if l.get("normalized") in vocab}
            identifier_col = f == "sibling_in_study" and (("identifier" in str(c.get("note", "")).lower()) or not legend)
            if identifier_col:
                # shared identifier among mapped rows -> yes when >=2 distinct sample-subjects share it
                vals = {}
                for ri, sk in tb["hits"].items():
                    raw = body[ri][j] if j < len(body[ri]) else None
                    if raw in (None, "") or RX.is_null(raw): continue
                    vals.setdefault(str(raw).strip(), set()).update(tb["subj_of"].get(ri, [ri]))
                for ri, sk in tb["hits"].items():
                    raw = body[ri][j] if j < len(body[ri]) else None
                    if raw in (None, "") or RX.is_null(raw): continue
                    n = len(vals[str(raw).strip()])
                    if n < 2: continue          # never assert 'no' from a supplement identifier column
                    for tk in (sk if isinstance(sk, list) else [sk]):
                        rows.append(_row(tb, tk, f, raw, "yes", 0.75, c["header"], ri, f"identifier shared by {n} mapped subjects"))
                continue
            for ri, sk in tb["hits"].items():
                raw = body[ri][j] if j < len(body[ri]) else None
                if raw in (None, ""): continue
                if f == "multiple_birth": val, note = norm_multiple_birth(raw, legend); conf = 0.85
                elif f == "sibling_in_study": val, note = norm_sibling(raw, legend); conf = 0.8
                elif f == "health_condition":
                    low = str(raw).strip().lower()
                    if legend and low in legend: val, note, conf = legend[low], "legend", 0.8
                    else:
                        m = cond_lookup.get((c["header"], str(raw).strip()))
                        val, conf, note = (m[0], min(m[1], 0.8), m[2]) if m else (None, 0, "no_norm")
                else:
                    m = geo_lookup.get((c["header"], str(raw).strip()))
                    val, conf, note = (m[0], min(m[1], 0.85), m[2]) if m else (None, 0, "no_norm")
                if val in (None, "unknown"): continue
                conf -= 0.1 if tb["pooled"] else 0.0
                conf -= 0.1 if tb["subject_level"] else 0.0
                for tk in (sk if isinstance(sk, list) else [sk]):
                    rows.append(_row(tb, tk, f, raw, val, round(conf, 2), c["header"], ri, note))
    return pd.DataFrame(rows)


def _row(tb, sk, f, raw, val, conf, header, ri, note):
    return dict(sample_key=sk, study_accession=tb["study_accession"], field_name=f, field_value=str(raw)[:120], value_normalized=str(val),
                confidence=float(conf), evidence_source="paper.supp.table", evidence_locator=f"{tb['pmcid']}/{tb['file']}/{tb['sheet']}!{header}:{ri + 1}",
                evidence_quote=RX.q12(f"{header}={str(raw)[:60]}"), evidence_limited_to_abstract=0.0, determined_by="r2_ext_haiku_cols+det_norm", route="R2",
                scope="subject" if tb["subject_level"] else "sample",
                parse_note=f"{note}; map={tb['method']}{'; pooled' if tb['pooled'] else ''}{'; subject_level_join' if tb['subject_level'] else ''}",
                group_audit=None, src_track="ext_r2", pmcid=tb["pmcid"], relation=tb["relation"], pooled=tb["pooled"])

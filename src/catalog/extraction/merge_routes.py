"""Merge R1' > R2 > R3 > R4 into one determination per sample x field; detect conflicts; Opus adjudication.

Inputs: per-route determination frames with columns
  sample_key, study_accession, field_name, field_value, value_normalized, confidence, evidence_source,
  evidence_locator, evidence_quote, determined_by, route (+ scope, evidence_limited_to_abstract, parse_note)
Outputs: candidates (all rows), conflicts (sample x field with disagreeing routes + decision), determinations.
Conflict = different normalized values across routes (categoricals) or age difference > max(7 d, 10 %).
Adjudication (Opus, 4 conflicts per request) is run on a per-(study, field, value-pair) *pattern* basis: identical
conflicts across many samples of one study share one decision (recorded with n_samples).
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
import json, re
import pandas as pd, numpy as np
import llm_batch_common as LBC

OPUS = resolve_model("adjudicate")
ROUTE_RANK = {"R1": 0, "R2": 1, "R3": 2, "R4": 3}
FEED_FIX = {"weaned/solids": "weaned"}
COLS = ["sample_key", "study_accession", "field_name", "field_value", "value_normalized", "confidence", "evidence_source",
        "evidence_locator", "evidence_quote", "evidence_limited_to_abstract", "determined_by", "route", "scope", "parse_note"]


def _std(df, route):
    d = df.copy()
    d["route"] = route
    for c in COLS:
        if c not in d:
            d[c] = None
    d["scope"] = d["scope"].fillna("sample")
    d["evidence_limited_to_abstract"] = d["evidence_limited_to_abstract"].fillna(0).astype(int)
    d["value_normalized"] = d["value_normalized"].astype(str).str.strip().replace(FEED_FIX)
    return d[COLS]


def age_conflict(a, b):
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        return True
    return abs(a - b) > max(7.0, 0.1 * max(a, b))


def merge(route_frames, samples):
    """route_frames: dict route -> DataFrame. Returns (candidates, conflict_patterns, determinations_pre_adjudication)."""
    cands = pd.concat([_std(df, r) for r, df in route_frames.items() if df is not None and len(df)], ignore_index=True)
    cands = cands[cands.value_normalized.notna() & ~cands.value_normalized.isin(["", "None", "nan"])]
    cands["_rank"] = cands.route.map(ROUTE_RANK)
    cands = cands.sort_values(["sample_key", "field_name", "_rank", "confidence"], ascending=[True, True, True, False])
    # conflicts across routes
    conf_rows = []
    for (sk, f), g in cands.groupby(["sample_key", "field_name"], sort=False):
        if g.route.nunique() < 2:
            continue
        top = g.iloc[0]
        others = g[g.route != top.route].drop_duplicates("route")
        for o in others.itertuples(index=False):
            diff = age_conflict(top.value_normalized, o.value_normalized) if f == "age_at_collection_days" else (top.value_normalized != o.value_normalized)
            if f in ("subject_id", "timepoint_label"):
                diff = False
            if diff:
                conf_rows.append(dict(sample_key=sk, study_accession=top.study_accession, field_name=f, route_a=top.route, value_a=top.value_normalized, quote_a=top.evidence_quote, source_a=top.evidence_source, locator_a=top.evidence_locator, conf_a=top.confidence,
                                      route_b=o.route, value_b=o.value_normalized, quote_b=o.evidence_quote, source_b=o.evidence_source, locator_b=o.evidence_locator, conf_b=o.confidence))
    conflicts = pd.DataFrame(conf_rows)
    det = cands.drop_duplicates(["sample_key", "field_name"]).drop(columns="_rank").copy()
    return cands.drop(columns="_rank"), conflicts, det


TOOL = {"name": "adjudicate", "description": "Decide conflicting metadata values.",
        "input_schema": {"type": "object", "properties": {"decisions": {"type": "array", "items": {"type": "object", "properties": {
            "conflict_id": {"type": "string"}, "decision": {"type": "string", "enum": ["a", "b", "neither", "both_compatible"]},
            "final_value": {"type": "string"}, "confidence": {"type": "number"}, "rationale": {"type": "string"}}, "required": ["conflict_id", "decision", "confidence", "rationale"]}}}, "required": ["decisions"]}}

ADJ_SYSTEM = """You adjudicate conflicts between two metadata determinations for infant gut microbiome samples. Each conflict gives the field, two candidate values, and for each the route (R1 = archive sample attribute / sample name, R2 = per-sample supplementary table of a linked paper, R3 = group-level statement in the paper's prose, R4 = abstract-only), the evidence source/locator and the verbatim quote. Decide which value the evidence supports: 'a', 'b', 'neither' (both quotes fail to support their value), or 'both_compatible' (e.g. c_section vs c_section_emergency, or ages within rounding). Prefer per-sample evidence (R1/R2) over group-level statements unless the group statement is explicit and the per-sample quote is ambiguous or mis-parsed (e.g. an age quoted from a subject ordinal, a unit mismatch, a table column that is really gestational or maternal age). Give final_value in the normalized vocabulary and a one-sentence rationale. Never use outside knowledge about the cohort; judge only the quoted evidence."""


def adjudicate(conflicts, host, per_request=4, max_patterns=None, out_path="pilot_conflicts_adjudication_log.parquet"):
    """Group identical conflicts into patterns (study, field, value_a, value_b, route_a, route_b, quote_a, quote_b) and let Opus decide each pattern once."""
    LBC.HOST = host
    if conflicts is None or not len(conflicts):
        return conflicts, {"requests": 0, "tokens": 0}
    key = ["study_accession", "field_name", "route_a", "value_a", "route_b", "value_b", "source_a", "source_b"]
    pats = conflicts.groupby(key, dropna=False).agg(n_samples=("sample_key", "size"), quote_a=("quote_a", "first"), quote_b=("quote_b", "first"), locator_a=("locator_a", "first"), locator_b=("locator_b", "first"), conf_a=("conf_a", "first"), conf_b=("conf_b", "first")).reset_index()
    pats = pats.sort_values("n_samples", ascending=False).reset_index(drop=True)
    pats["conflict_id"] = [f"C{i}" for i in range(len(pats))]
    todo = pats if max_patterns is None else pats.head(max_patterns)
    reqs, metas = [], []
    for i in range(0, len(todo), per_request):
        chunk = todo.iloc[i:i + per_request]
        txt = "\n\n".join(f"CONFLICT {r.conflict_id} (study {r.study_accession}, field {r.field_name}, {r.n_samples} samples)\n A: route {r.route_a} value={r.value_a} conf={r.conf_a} source={r.source_a} locator={r.locator_a}\n    quote: \"{r.quote_a}\"\n B: route {r.route_b} value={r.value_b} conf={r.conf_b} source={r.source_b} locator={r.locator_b}\n    quote: \"{r.quote_b}\"" for r in chunk.itertuples())
        reqs.append({"model": OPUS, "system": ADJ_SYSTEM, "max_tokens": 1500, "tools": [TOOL], "tool_choice": {"type": "tool", "name": "adjudicate"},
                     "messages": [{"role": "user", "content": txt + "\n\nReturn one decision per conflict_id."}]})
        metas.append({"ids": chunk.conflict_id.tolist(), "slots": ["adjudication"]})
    decisions = {}

    def make_rows(meta, parsed, res):
        out = []
        for d in parsed.get("decisions", []) or []:
            if not isinstance(d, dict):
                continue
            decisions[d.get("conflict_id")] = d
            out.append({"record_id": d.get("conflict_id"), "slot": "adjudication", "value": d.get("decision"), "outcome": "unsure_adjudicated", "confidence": min(float(d.get("confidence", 0.5)), 1.0),
                        "evidence": [{"source": "paper.supp.table", "quote": " ".join(str(d.get("rationale", ""))[:80].split()[:12])}], "model": OPUS, "note": d.get("rationale")})
        for cid in meta["ids"]:
            if cid not in decisions:
                out.append(LBC.V["sentinel_row"](cid, "adjudication", OPUS, note="missing_from_batch"))
        return out
    _, stats = LBC.run_batches(reqs, metas, make_rows, out_path, OPUS, max_concurrency=4)
    pats["decision"] = pats.conflict_id.map(lambda c: decisions.get(c, {}).get("decision", "not_adjudicated"))
    pats["final_value"] = pats.conflict_id.map(lambda c: decisions.get(c, {}).get("final_value"))
    pats["adj_confidence"] = pats.conflict_id.map(lambda c: decisions.get(c, {}).get("confidence"))
    pats["rationale"] = pats.conflict_id.map(lambda c: decisions.get(c, {}).get("rationale"))
    conflicts = conflicts.merge(pats[key + ["conflict_id", "n_samples", "decision", "final_value", "adj_confidence", "rationale"]], on=key, how="left")
    return conflicts, stats


def apply_decisions(det, conflicts):
    """Replace the precedence winner where Opus chose b or neither."""
    if conflicts is None or not len(conflicts) or "decision" not in conflicts:
        return det
    det = det.set_index(["sample_key", "field_name"])
    drop = []
    for r in conflicts.itertuples(index=False):
        k = (r.sample_key, r.field_name)
        if k not in det.index:
            continue
        if r.decision == "b":
            det.loc[k, ["value_normalized", "confidence", "evidence_source", "evidence_locator", "evidence_quote", "route", "determined_by"]] = [r.value_b, r.conf_b, r.source_b, r.locator_b, r.quote_b, r.route_b, "opus_adjudicated"]
        elif r.decision == "neither":
            drop.append(k)
        elif r.decision in ("a", "both_compatible"):
            det.loc[k, "determined_by"] = str(det.loc[k, "determined_by"]) + "|adjudicated_a"
    if drop:
        det = det.drop(index=[k for k in drop if k in det.index])
    return det.reset_index()


# ---------------------------------------------------------------- pilot fixes F4/F5 (group-level routes)
THRESH_RX = re.compile(r"prior to|before|less than|more than|at least|minimum|maximum|<|>|≤|≥|under|over|below|above|between", re.I)


def threshold_filter(group_det):
    """F5: numeric GA/BW and preterm statements quoted from threshold phrasing are dropped."""
    if group_det is None or not len(group_det):
        return group_det
    bad = group_det.field_name.isin(["gestational_age_weeks", "birth_weight_grams", "preterm_status"]) & group_det.evidence_quote.fillna("").str.contains(THRESH_RX)
    # a 'term' verdict from ">= 37 weeks" style thresholds is fine
    ok_term = (group_det.field_name == "preterm_status") & (group_det.value_normalized == "term") & group_det.evidence_quote.fillna("").str.contains(r"3[7-9]|4[0-2]\s*weeks|full[- ]term|\bterm\b", regex=True)
    return group_det[~(bad & ~ok_term)].copy()


def consistency_filter(group_det, sample_det, min_overlap=5, max_disagree=0.2):
    """F4: a group-level statement (same study, field, value, applies_to, quote) is dropped when it disagrees with
    per-sample R1/R2 values on > max_disagree of >= min_overlap overlapping samples. Returns (kept, dropped_summary)."""
    if group_det is None or not len(group_det):
        return group_det, pd.DataFrame()
    g = group_det.copy()
    g["_stmt"] = g.study_accession + "|" + g.field_name + "|" + g.value_normalized.astype(str) + "|" + g.get("applies_to", pd.Series("", index=g.index)).astype(str) + "|" + g.evidence_quote.astype(str)
    s = sample_det[["sample_key", "field_name", "value_normalized"]].rename(columns={"value_normalized": "_sv"})
    m = g.merge(s, on=["sample_key", "field_name"], how="left")
    m["_dis"] = [(age_conflict(a, b) if f == "age_at_collection_days" else (str(a) != str(b))) if isinstance(b, str) else np.nan for f, a, b in zip(m.field_name, m.value_normalized, m._sv)]
    summ = m.groupby("_stmt").agg(n=("sample_key", "size"), overlap=("_dis", "count"), disagree=("_dis", "mean")).reset_index()
    drop = set(summ[(summ.overlap >= min_overlap) & (summ.disagree > max_disagree)]._stmt)
    kept = g[~g._stmt.isin(drop)].drop(columns="_stmt")
    summ["dropped"] = summ._stmt.isin(drop)
    return kept, summ

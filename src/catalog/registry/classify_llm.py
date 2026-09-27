"""LLM classification stage of the registry: Sonnet ×2 replicates → Opus adjudication on disagreement.

Same machinery as the infant triage (catalog.triage.llm_batch_common): JSON tool output, every id returned or a sentinel
row, validate_evidence on every evidence row, cost logging. Models come from catalog.models roles (config/models.yaml:
``rubric`` = Sonnet-class replicate, ``adjudicate`` = Opus-class) — NO literal model ids. ``host.llm`` is used when a
``host`` object is passed (leaf-worker convention: the root session passes ``host``); the pure functions (batch builder,
parser, validator, agreement) are host-free and unit-tested on synthetic responses (tests/test_registry.py).

Pipeline for a frame of candidate studies (needs_llm == True from classify_deterministic):
    batches = build_batches(records, batch_size=6)
    reqs    = [make_request(b, model, system) for b in batches]
    res     = host.llm(reqs, max_concurrency=8)             # replicate 1; repeat for replicate 2
    rows    = parse_and_validate(res_i, batch.ids)           # one dict per id (sentinel when missing / invalid)
    merged  = merge_replicates(rows_rep1, rows_rep2)         # agreement → stage sonnet_x2; disagreement → adjudication queue
    adj     = adjudicate(disagreements, host, ...)           # Opus, 1 batch of ≤ 6, stage opus_adjudicated
Output columns match registry_studies (host_human, assay, body_sites, body_site_primary, life_stages, life_stage_primary,
population_flags, health_context, *_evidence json, classification_stage, classification_confidence, classification_model).
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

from catalog.triage.curation_kernel import validate_evidence
from catalog.registry import vocab as V

_HERE = os.path.dirname(os.path.abspath(__file__))
PROMPT_DIR = os.path.join(_HERE, "prompts")
BATCH_SIZE = 6
MAX_TOKENS_REPLICATE = 6000
MAX_TOKENS_ADJUDICATE = 8000
DECISIONS = ("host_human", "assay", "body_site", "life_stage")
HOST_VALUES = ("yes", "no", "mixed", "unknown")
SENTINELS = {"host_human": "unknown", "assay": "unknown", "body_site_primary": "unknown_site", "life_stage_primary": "unknown_age"}
ALLOWED_SOURCES = ("study.title", "study.description", "sample.title", "sample.attr.", "run.")
RECORD_FIELDS = ["study_accession", "study_title", "description", "n_runs", "n_samples", "library_strategies", "library_sources",
                 "target_genes", "instrument_models", "base_count_median", "read_length_median", "scientific_names", "host_tax_ids",
                 "host_scientific_names", "host_body_sites", "isolation_sources", "environmental_medium", "sample_titles", "ages",
                 "dev_stages", "serovars", "sub_species", "strains", "deterministic_hint"]


# --------------------------------------------------------------------------- prompts / schema
def load_prompt(name: str) -> str:
    for cand in (name, os.path.join(PROMPT_DIR, name)):  # cwd copy first (leaf-worker convention)
        if os.path.exists(cand):
            return open(cand, encoding="utf-8").read()
    raise FileNotFoundError(name)


def output_schema() -> dict:
    ev = {"type": "array", "items": {"type": "object", "properties": {"source": {"type": "string"}, "quote": {"type": "string"}},
                                     "required": ["source", "quote"]}}
    study = {"type": "object", "properties": {
        "study_accession": {"type": "string"},
        "host_human": {"type": "string", "enum": list(HOST_VALUES)},
        "assay": {"type": "string", "enum": V.codes("assay")},
        "body_sites": {"type": "array", "items": {"type": "string", "enum": V.codes("body_sites")}},
        "body_site_primary": {"type": "string", "enum": V.codes("body_sites")},
        "life_stages": {"type": "array", "items": {"type": "string", "enum": V.codes("life_stages")}},
        "life_stage_primary": {"type": "string", "enum": V.codes("life_stages")},
        "population_flags": {"type": "array", "items": {"type": "string", "enum": V.codes("population_flags")}},
        "health_context": {"type": ["string", "null"], "maxLength": 120},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "evidence": {"type": "object", "properties": {"host_human": ev, "assay": ev, "body_site": ev, "life_stage": ev,
                                                      "population_flags": {"type": "object", "additionalProperties": ev}},
                     "required": ["host_human", "assay", "body_site", "life_stage"]},
    }, "required": ["study_accession", "host_human", "assay", "body_sites", "body_site_primary", "life_stages",
                    "life_stage_primary", "population_flags", "confidence", "evidence"]}
    return {"type": "object", "properties": {"studies": {"type": "array", "items": study}}, "required": ["studies"]}


TOOL = {"name": "registry_classification", "description": "Return the classification of every study in the batch.",
        "input_schema": None}  # filled lazily (vocab must load first)


def tool_spec() -> dict:
    t = dict(TOOL)
    t["input_schema"] = output_schema()
    return t


# --------------------------------------------------------------------------- batch builder
def compact_record(rec: dict, det: dict | None = None, max_desc: int = 1200, max_titles: int = 8) -> dict:
    """Aggregated study record → compact JSON for the prompt (blank fields dropped)."""
    from catalog.registry.classify_deterministic import split_multi, _s

    out: dict[str, Any] = {"study_accession": rec.get("study_accession"), "study_title": _s(rec.get("study_title"))[:300]}
    d = _s(rec.get("description"))
    if d:
        out["description"] = d[:max_desc]
    for k in ("n_runs", "n_samples", "base_count_median", "read_length_median"):
        v = rec.get(k)
        if v not in (None, "") and str(v) != "nan":
            out[k] = v
    ls = _s(rec.get("library_strategies"))
    if ls:
        try:
            out["library_strategies"] = json.loads(ls) if ls.startswith("{") else split_multi(ls)
        except json.JSONDecodeError:
            out["library_strategies"] = split_multi(ls)
    for k in ("library_sources", "target_genes", "instrument_models", "host_tax_ids", "host_scientific_names", "host_body_sites",
              "isolation_sources", "environmental_medium", "ages", "dev_stages", "serovars", "sub_species", "strains"):
        vals = split_multi(rec.get(k))
        if vals:
            out[k] = vals[:10]
    sci = split_multi(rec.get("scientific_names"))
    if sci:
        out["scientific_names"] = sci[:5]
    titles = split_multi(rec.get("sample_titles_sample") or rec.get("sample_titles"))
    if titles:
        out["sample_titles"] = titles[:max_titles]
    if det:
        out["deterministic_hint"] = {k: det.get(k) for k in ("host_human", "assay", "body_site_primary", "life_stage_primary",
                                                             "needs_llm_reasons") if det.get(k) not in (None, "", [])}
    return out


def build_batches(records: list[dict], dets: dict[str, dict] | None = None, batch_size: int = BATCH_SIZE) -> list[dict]:
    """→ [{ids: [...], records: [compact...]}, ...]; ≤ batch_size studies per request (Rule 13: small batches)."""
    batches = []
    for i in range(0, len(records), batch_size):
        chunk = records[i:i + batch_size]
        comp = [compact_record(r, (dets or {}).get(r.get("study_accession"))) for r in chunk]
        batches.append({"ids": [r.get("study_accession") for r in chunk], "records": comp})
    return batches


def make_request(batch: dict, model: str, system: str | None = None, max_tokens: int = MAX_TOKENS_REPLICATE,
                 force_tool: bool = True) -> dict:
    """force_tool=False for the adjudication (Opus-class) model: it rejects tool_choice type "tool"/"any" (API 400,
    observed 2026-09-27); with tool_choice auto the tool is still called because the user prompt asks for it, and
    tool_input() falls back to parsing JSON from the text."""
    system = system if system is not None else load_prompt("classify_system.txt")
    tmpl = load_prompt("classify_user_template.txt")
    user = tmpl.format(n_studies=len(batch["ids"]), ids=", ".join(batch["ids"]),
                       records_json=json.dumps(batch["records"], ensure_ascii=False, separators=(",", ":")))
    if not force_tool:
        user += "\n\nCall the registry_classification tool with your answer (or, if you cannot call tools, reply with ONLY the JSON object)."
    return {"prompt": user, "system": system, "model": model, "max_tokens": max_tokens,
            "tools": [tool_spec()], "tool_choice": {"type": "tool", "name": TOOL["name"]} if force_tool else {"type": "auto"}}


# --------------------------------------------------------------------------- parser / validator
def tool_input(res: Any) -> dict | None:
    """Tolerant extraction of the JSON object from a host.llm result (tool_use first, then text)."""
    if isinstance(res, str):
        res = {"text": res}
    if not isinstance(res, dict) or res.get("error"):
        return None
    tu = res.get("tool_use")
    if isinstance(tu, list) and tu:
        tu = tu[0]
    if isinstance(tu, dict):
        return tu.get("input", tu)
    for blk in res.get("content") or []:
        if isinstance(blk, dict) and blk.get("type") == "tool_use":
            return blk.get("input")
    t = res.get("text") or ""
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        return json.loads(t[i:j + 1])
    except json.JSONDecodeError:
        return None


def usage_tokens(res: Any) -> int:
    u = (res or {}).get("usage") if isinstance(res, dict) else None
    u = u or {}
    return int(u.get("input_tokens", 0) or 0) + int(u.get("output_tokens", 0) or 0)


def sentinel(study_accession: str, model: str, note: str) -> dict:
    return {"study_accession": study_accession, "host_human": "unknown", "assay": "unknown", "body_sites": ["unknown_site"],
            "body_site_primary": "unknown_site", "life_stages": ["unknown_age"], "life_stage_primary": "unknown_age",
            "population_flags": [], "health_context": None, "confidence": 0.0,
            "evidence": {"host_human": [], "assay": [], "body_site": [], "life_stage": [], "population_flags": {}},
            "model": model, "outcome": "sentinel_no_evidence", "note": note}


def _valid_source(src: str) -> bool:
    return any(str(src).startswith(p) for p in ALLOWED_SOURCES)


def validate_study(obj: dict, model: str) -> tuple[dict, list[str]]:
    """Vocabulary + evidence checks. Returns (row, problems). A problem on a decision downgrades THAT decision to its
    sentinel (never the whole study); a structural problem downgrades the whole row to validator_rejected."""
    problems: list[str] = []
    acc = obj.get("study_accession")
    if not isinstance(acc, str) or not acc:
        return sentinel(str(acc), model, "missing study_accession"), ["missing study_accession"]
    row = sentinel(acc, model, "")
    row["outcome"] = "predicted"
    row["note"] = None
    ev = obj.get("evidence") if isinstance(obj.get("evidence"), dict) else {}

    def check_ev(rows: Any, label: str) -> bool:
        if not isinstance(rows, list) or not rows:
            problems.append(f"{label}: no evidence")
            return False
        ok, msg = validate_evidence(rows)
        if not ok:
            problems.append(f"{label}: {msg}")
            return False
        if not all(_valid_source(r.get("source")) for r in rows):
            problems.append(f"{label}: source not in allowed registry list")
            return False
        return True

    # host
    hv = obj.get("host_human")
    if hv not in HOST_VALUES:
        problems.append(f"host_human: bad value {hv!r}")
    elif hv != "unknown" and check_ev(ev.get("host_human"), "host_human"):
        row["host_human"], row["evidence"]["host_human"] = hv, ev["host_human"]
    elif hv == "unknown":
        row["host_human"] = "unknown"
    # assay
    av = obj.get("assay")
    if av not in V.codes("assay"):
        problems.append(f"assay: bad value {av!r}")
    elif av != "unknown" and check_ev(ev.get("assay"), "assay"):
        row["assay"], row["evidence"]["assay"] = av, ev["assay"]
    # body site
    bs = obj.get("body_sites") if isinstance(obj.get("body_sites"), list) else []
    bp = obj.get("body_site_primary")
    ok_codes, msg = V.validate_codes("body_sites", bs + ([bp] if bp else []))
    if not ok_codes:
        problems.append(msg)
    elif bp and bp != "unknown_site" and check_ev(ev.get("body_site"), "body_site"):
        row["body_sites"] = list(dict.fromkeys(bs or [bp]))
        row["body_site_primary"], row["evidence"]["body_site"] = bp, ev["body_site"]
    # life stage
    lst = obj.get("life_stages") if isinstance(obj.get("life_stages"), list) else []
    lp = obj.get("life_stage_primary")
    ok_codes, msg = V.validate_codes("life_stages", lst + ([lp] if lp else []))
    if not ok_codes:
        problems.append(msg)
    elif lp and lp != "unknown_age" and check_ev(ev.get("life_stage"), "life_stage"):
        row["life_stages"] = list(dict.fromkeys(lst or [lp]))
        row["life_stage_primary"], row["evidence"]["life_stage"] = lp, ev["life_stage"]
    if row["host_human"] == "no":  # animals carry no human site / life stage
        row["body_sites"], row["body_site_primary"], row["life_stages"], row["life_stage_primary"] = [], None, [], None
    # population flags
    pf = obj.get("population_flags") if isinstance(obj.get("population_flags"), list) else []
    ok_codes, msg = V.validate_codes("population_flags", pf)
    if not ok_codes:
        problems.append(msg)
    else:
        pev = ev.get("population_flags") if isinstance(ev.get("population_flags"), dict) else {}
        for f in pf:
            if check_ev(pev.get(f), f"population_flags.{f}"):
                row["population_flags"].append(f)
                row["evidence"]["population_flags"][f] = pev[f]
    hc = obj.get("health_context")
    row["health_context"] = (str(hc)[:120] if hc else None)
    try:
        c = float(obj.get("confidence", 0))
        row["confidence"] = min(max(c, 0.0), 1.0)
    except (TypeError, ValueError):
        problems.append("confidence not numeric")
        row["confidence"] = 0.0
    if problems:
        row["note"] = "; ".join(problems)[:500]
        if any(p.startswith(("host_human: bad", "assay: bad")) or "unknown codes" in p for p in problems):
            row["outcome"] = "validator_rejected"
    return row, problems


def parse_and_validate(res: Any, ids: list[str], model: str) -> tuple[list[dict], dict]:
    """host.llm result for ONE batch → one validated row per requested id (sentinel for missing / extra ids dropped)."""
    stats = {"tokens": usage_tokens(res), "missing": 0, "extra": 0, "problems": 0, "unparsable": 0}
    parsed = tool_input(res)
    if not parsed or not isinstance(parsed.get("studies"), list):
        stats["unparsable"] = 1
        return [sentinel(i, model, "llm_error_or_unparsable") for i in ids], stats
    by_id: dict[str, dict] = {}
    for obj in parsed["studies"]:
        if isinstance(obj, dict) and obj.get("study_accession") in ids and obj["study_accession"] not in by_id:
            by_id[obj["study_accession"]] = obj
        else:
            stats["extra"] += 1
    rows = []
    for i in ids:
        if i not in by_id:
            stats["missing"] += 1
            rows.append(sentinel(i, model, "registry_classify_missing"))
            continue
        row, probs = validate_study(by_id[i], model)
        stats["problems"] += len(probs)
        rows.append(row)
    return rows, stats


# --------------------------------------------------------------------------- replicate agreement / adjudication
def _key(row: dict) -> tuple:
    return (row["host_human"], row["assay"], row["body_site_primary"], row["life_stage_primary"])


def agree(a: dict, b: dict) -> bool:
    """Replicates agree when host, assay, primary body site and primary life stage all match and neither is a sentinel."""
    return _key(a) == _key(b) and a["outcome"] == b["outcome"] == "predicted"


def merge_replicates(rep1: list[dict], rep2: list[dict], model: str) -> tuple[list[dict], list[str]]:
    """→ (merged rows, ids needing adjudication). Agreement → stage sonnet_x2 with the higher-confidence replicate's
    evidence and confidence = mean; disagreement → the row is kept as `pending` and the id is queued."""
    b = {r["study_accession"]: r for r in rep2}
    merged, queue = [], []
    for r1 in rep1:
        r2 = b.get(r1["study_accession"])
        if r2 is None:
            queue.append(r1["study_accession"])
            r1 = dict(r1, classification_stage="pending")
            merged.append(r1)
            continue
        if agree(r1, r2):
            best = r1 if r1["confidence"] >= r2["confidence"] else r2
            row = dict(best)
            row["population_flags"] = sorted(set(r1["population_flags"]) | set(r2["population_flags"]))
            row["evidence"] = dict(best["evidence"])
            row["evidence"]["population_flags"] = {**r2["evidence"].get("population_flags", {}), **r1["evidence"].get("population_flags", {})}
            row["confidence"] = round((r1["confidence"] + r2["confidence"]) / 2, 3)
            row["classification_stage"] = "sonnet_x2"
            row["classification_model"] = model
            merged.append(row)
        else:
            queue.append(r1["study_accession"])
            row = dict(r1, classification_stage="pending", classification_model=model)
            row["note"] = f"replicate disagreement: {_key(r1)} vs {_key(r2)}"
            merged.append(row)
    return merged, queue


def adjudication_hint(r1: dict, r2: dict) -> dict:
    return {"replicate_1": {k: r1[k] for k in ("host_human", "assay", "body_site_primary", "life_stage_primary")},
            "replicate_2": {k: r2[k] for k in ("host_human", "assay", "body_site_primary", "life_stage_primary")},
            "needs_llm_reasons": ["replicate_disagreement"]}


# --------------------------------------------------------------------------- driver (host.llm)
class CostLog:
    def __init__(self, path: str | None = None):
        self.path, self.t0 = path, time.time()
        self.calls: list[dict] = []

    def add(self, stage: str, model: str, n_studies: int, tokens: int, **extra):
        self.calls.append({"stage": stage, "model": model, "n_studies": n_studies, "tokens": tokens, "t": round(time.time() - self.t0, 1), **extra})
        if self.path:
            json.dump(self.summary(), open(self.path, "w"), indent=1)

    def summary(self) -> dict:
        by = {}
        for c in self.calls:
            s = by.setdefault(c["stage"], {"requests": 0, "studies": 0, "tokens": 0})
            s["requests"] += 1
            s["studies"] += c["n_studies"]
            s["tokens"] += c["tokens"]
        for s in by.values():
            s["tokens_per_study"] = round(s["tokens"] / s["studies"], 1) if s["studies"] else None
        return {"stages": by, "total_tokens": sum(c["tokens"] for c in self.calls), "seconds": round(time.time() - self.t0), "calls": self.calls}


def resolve_models(host=None) -> dict[str, str]:
    from catalog.models import resolve_model, set_host

    set_host(host)
    return {"replicate": resolve_model("rubric"), "adjudicate": resolve_model("adjudicate")}


def run_llm_stage(records: list[dict], dets: dict[str, dict] | None, host, out_json: str | None = None,
                  batch_size: int = BATCH_SIZE, max_concurrency: int = 8, log_path: str | None = None) -> list[dict]:
    """Sonnet ×2 → Opus adjudication for a list of aggregated study records. Requires the kernel ``host`` (root-dispatched
    leaf worker). Returns registry-shaped rows (one per input study)."""
    assert host is not None, "run_llm_stage needs the kernel host object (leaf-worker convention)"
    models = resolve_models(host)
    log = CostLog(log_path)
    system = load_prompt("classify_system.txt")
    batches = build_batches(records, dets, batch_size)
    reps: list[list[dict]] = []
    for rep in (1, 2):
        reqs = [make_request(b, models["replicate"], system) for b in batches]
        rows: list[dict] = []
        for i in range(0, len(reqs), max_concurrency * 2):
            results = host.llm(reqs[i:i + max_concurrency * 2], max_concurrency=max_concurrency)
            for b, res in zip(batches[i:i + max_concurrency * 2], results):
                r, st = parse_and_validate(res, b["ids"], models["replicate"])
                log.add(f"sonnet_rep{rep}", models["replicate"], len(b["ids"]), st["tokens"], missing=st["missing"], problems=st["problems"])
                rows.extend(r)
        reps.append(rows)
    merged, queue = merge_replicates(reps[0], reps[1], models["replicate"])
    if queue:
        r1 = {r["study_accession"]: r for r in reps[0]}
        r2 = {r["study_accession"]: r for r in reps[1]}
        recs = {r["study_accession"]: r for r in records}
        hints = {i: {**((dets or {}).get(i) or {}), **adjudication_hint(r1[i], r2.get(i, r1[i]))} for i in queue}
        abatches = build_batches([recs[i] for i in queue], hints, batch_size)
        areqs = [make_request(b, models["adjudicate"], system, MAX_TOKENS_ADJUDICATE, force_tool=False) for b in abatches]
        results = host.llm(areqs, max_concurrency=max(1, max_concurrency // 2))
        adj: dict[str, dict] = {}
        for b, res in zip(abatches, results):
            rows, st = parse_and_validate(res, b["ids"], models["adjudicate"])
            log.add("opus_adjudicate", models["adjudicate"], len(b["ids"]), st["tokens"], missing=st["missing"], problems=st["problems"])
            for r in rows:
                r["classification_stage"] = "opus_adjudicated" if r["outcome"] == "predicted" else "pending"
                r["classification_model"] = models["adjudicate"]
                adj[r["study_accession"]] = r
        merged = [adj.get(r["study_accession"], r) if r["study_accession"] in queue else r for r in merged]
    out = [to_registry_row(r) for r in merged]
    if out_json:
        json.dump({"rows": out, "cost": log.summary()}, open(out_json, "w"), indent=1)
    return out


def to_registry_row(r: dict) -> dict:
    """LLM row → registry_studies column conventions (';'-joined lists, JSON evidence)."""
    ev = r.get("evidence") or {}
    return {"study_accession": r["study_accession"], "host_human": r["host_human"], "host_evidence": json.dumps(ev.get("host_human", [])),
            "assay": r["assay"], "assay_evidence": json.dumps(ev.get("assay", [])),
            "body_sites": ";".join(r.get("body_sites") or []), "body_site_primary": r.get("body_site_primary"),
            "body_site_evidence": json.dumps(ev.get("body_site", [])),
            "life_stages": ";".join(r.get("life_stages") or []), "life_stage_primary": r.get("life_stage_primary"),
            "life_stage_evidence": json.dumps(ev.get("life_stage", [])),
            "population_flags": ";".join(r.get("population_flags") or []), "population_evidence": json.dumps(ev.get("population_flags", {})),
            "health_context": r.get("health_context"), "classification_stage": r.get("classification_stage", "pending"),
            "classification_confidence": r.get("confidence", 0.0), "classification_model": r.get("classification_model", r.get("model")),
            "outcome": r.get("outcome"), "note": r.get("note")}

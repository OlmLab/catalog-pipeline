"""Sonnet adjudication of contested paper<->study links. One request per paper covering all its contested studies."""
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
import json, re, time
import pandas as pd

SYSTEM = (
 "You are a data-provenance curator linking scientific papers to sequencing archive studies (ENA/SRA BioProjects). "
 "For each candidate study you are shown the archive record (accession, archive title, sample count, first-public date) and the "
 "text windows from the paper where its accessions appear (labelled by paper section). Decide the paper's relation to that study:\n"
 " own_data: the paper's authors generated and deposited this dataset (typical cues: 'deposited', 'submitted', 'have been uploaded', 'are available under accession', in a Data Availability/Methods statement, archive title matching the paper's cohort, first-public date close to the paper).\n"
 " reused_public_data: the paper analysed this dataset but did not generate it ('downloaded', 'obtained from', 'publicly available', 'previously published', meta-analysis, archive first-public well before the paper, archive title naming a different cohort/author).\n"
 " cited_only: the accession is mentioned as background/comparison without analysing it, or in a reference list.\n"
 " unsure: the windows do not allow a decision.\n"
 "Use ONLY the supplied text. Do not use knowledge about the paper or the accession from memory. For each study give a quote of at most 12 words copied verbatim from one supplied window (or the title/abstract) and the label of the window it came from "
 "(one of the section labels shown, e.g. 'paper.fulltext.data_availability', 'paper.fulltext.methods', 'paper.fulltext.results', 'paper.supp.<file>', 'paper.abstract', 'paper.title'). Give a confidence 0-1.\n"
 "Respond with ONLY a JSON array: [{\"study_accession\": ..., \"relation\": ..., \"quote\": ..., \"source\": ..., \"confidence\": ...}, ...] with one object per candidate study."
)

def _sec_label(sec):
    if str(sec).startswith("supplement:"):
        return "paper.supp." + str(sec).split(":", 1)[1][:60]
    if sec == "supplement":
        return "paper.supp.file"
    if sec == "abstract":
        return "paper.abstract"
    return f"paper.fulltext.{sec}"

def build_prompt(paper, cands, ctx_chars=450):
    """paper: dict(title, abstract, pubYear); cands: list of dict rows (study_accession, study_title, n_samples, first_public, accessions, sections, contexts)."""
    lines = [f"PAPER TITLE: {paper['title']}", f"PAPER YEAR: {paper.get('pubYear')}", f"ABSTRACT (first 600 chars): {str(paper.get('abstract') or '')[:600]}", "", f"CANDIDATE STUDIES ({len(cands)}):"]
    for c in cands:
        lines.append(f"--- study_accession={c['study_accession']} | archive title: {c['study_title']} | n_samples={c['n_samples']} | first_public={c['first_public']}")
        lines.append(f"    accessions seen in paper: {', '.join(list(c['accessions'])[:8])}; paper sections: {', '.join(_sec_label(s) for s in c['sections'])}")
        for i, (sec, ctx) in enumerate(zip(c.get("ctx_sections", c["sections"]), c["contexts"])):
            lines.append(f"    [{_sec_label(sec)}] ...{str(ctx)[:ctx_chars]}...")
    return "\n".join(lines)

def parse(text):
    m = re.search(r"\[.*\]", text or "", re.S)
    if not m:
        return []
    s = m.group(0)
    try:
        return json.loads(s)
    except Exception:
        try:
            return json.loads(re.sub(r",\s*([\]}])", r"\1", s))
        except Exception:
            return []

def run(host, validate_row, jobs, model, concurrency=4, max_tokens=3000):
    """jobs: list of dict(paper_id, pmcid, pmid, prompt, cands). Returns (rows, tokens)."""
    reqs = [{"prompt": j["prompt"], "system": SYSTEM, "model": model, "max_tokens": max_tokens} for j in jobs]
    t0 = time.time()
    res = host.llm(reqs, max_concurrency=concurrency)
    tin = tout = 0; nerr = 0; rows = []
    for j, r in zip(jobs, res):
        if not isinstance(r, dict) or "error" in r or not r.get("text"):
            nerr += 1
            for c in j["cands"]:
                rows.append({"record_id": f"{j['paper_id']}|{c['study_accession']}", "paper_id": j["paper_id"], "pmcid": j["pmcid"], "pmid": j["pmid"],
                             "study_accession": c["study_accession"], "slot": "relation", "value": None, "outcome": "sentinel_no_evidence",
                             "confidence": 0.0, "evidence": [], "model": model, "note": f"llm error: {str(r)[:200]}"})
            continue
        u = r.get("usage") or {}
        tin += int(u.get("input_tokens", 0)); tout += int(u.get("output_tokens", 0))
        by = {str(o.get("study_accession", "")).upper(): o for o in parse(r["text"]) if isinstance(o, dict)}
        for c in j["cands"]:
            o = by.get(c["study_accession"].upper())
            base = {"record_id": f"{j['paper_id']}|{c['study_accession']}", "paper_id": j["paper_id"], "pmcid": j["pmcid"], "pmid": j["pmid"],
                    "study_accession": c["study_accession"], "slot": "relation", "model": model, "note": None}
            if o is None:
                rows.append({**base, "value": None, "outcome": "sentinel_no_evidence", "confidence": 0.0, "evidence": [], "note": "study missing from LLM response"}); continue
            rel = str(o.get("relation", "unsure")).strip().lower()
            if rel not in ("own_data", "reused_public_data", "cited_only", "unsure"):
                rel = "unsure"
            q = str(o.get("quote") or "").strip().strip('"')
            q = " ".join(q.split()[:12])
            src = str(o.get("source") or "").strip()
            try:
                conf = max(0.0, min(1.0, float(o.get("confidence", 0.5))))
            except Exception:
                conf = 0.5
            row = {**base, "value": rel, "outcome": "predicted", "confidence": round(conf, 3), "evidence": [{"source": src, "quote": q}] if q else []}
            if not q:
                row["outcome"] = "sentinel_no_evidence"; row["note"] = "no quote"; row["value_unanchored"] = rel
            else:
                ok, msg = validate_row(row)
                if not ok:
                    row["outcome"] = "validator_rejected"; row["note"] = f"validate_row: {msg}"; row["value_unanchored"] = rel
            rows.append(row)
    tk = {"model": model, "requests": len(reqs), "request_errors": nerr, "input_tokens": tin, "output_tokens": tout, "total_tokens": tin + tout, "seconds": round(time.time() - t0)}
    return rows, tk

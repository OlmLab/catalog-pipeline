"""Batched abstract screen: 20 papers per host.llm request -> validated (record, slot) rows.
Usage inside a python cell (env infantcat, cwd on sys.path, infant-curation-rules kernel loaded):
    import screen_papers as SP
    SP.screen(slice_path, prefix, model, start=0, stop=None, batch=20, concurrency=5)
Writes ckpt/{prefix}_{start:05d}_{stop:05d}.parquet and tokens/{prefix}_{start}_{stop}.json.
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
import json, os, re, time
import pandas as pd

SLOTS = ["is_human", "has_infant_0_36m", "is_shotgun", "data_type"]
SYSTEM = (
 "You are a careful literature screener for a catalog of human infant gut shotgun-metagenome studies. "
 "You read ONLY the title and abstract given. Never use outside knowledge about a paper. "
 "For each paper answer four slots.\n"
 "is_human: true if the study subjects are humans (human samples, cohorts, patients, infants); false if animal/in-vitro/environmental only; 'unsure' if not stated.\n"
 "has_infant_0_36m: true if the study includes humans aged 0-36 months (newborn, neonate, infant, toddler, preterm, 'first 3 years', 'first year of life', birth cohort sampled in infancy, NICU). "
 "NOT true for 'children' without an age <=3y, for school-age children, for pregnant women only, or for animal pups/piglets/calves. false if humans studied but no infants; 'unsure' if age not stated.\n"
 "is_shotgun: true if shotgun metagenomic DNA sequencing was performed or analysed (shotgun metagenomics, whole-metagenome sequencing, WGS metagenomics, metagenome-assembled genomes, metagenomic sequencing of stool). "
 "false if the only sequencing is 16S/18S/ITS amplicon, qPCR, culture, metatranscriptomics/RNA-seq only, isolate whole-genome sequencing only, or no sequencing. 'unsure' if the abstract does not say how the microbiome was measured (e.g. 'sequencing' or 'microbiome profiling' unspecified).\n"
 "data_type: primary_new_data (authors generated new sequence data), reanalysis_of_public_data (analysis of existing public datasets only), review_or_method (review, commentary, protocol, software/method benchmark, meta-analysis without new data), or unsure.\n"
 "For each slot give a quote of at most 12 words copied verbatim from the title or abstract that supports your value, and its source: 'paper.title' or 'paper.abstract'. "
 "For a false value, quote the words showing what WAS studied instead (e.g. 'mice', '16S rRNA gene sequencing', 'adults aged 18-65'). "
 "Only when no words at all support the value (typically 'unsure'), set quote to ''. Give one confidence 0-1 for the whole paper.\n"
 "Respond with ONLY a JSON array, one object per paper, keys: id, is_human, human_quote, human_source, has_infant_0_36m, infant_quote, infant_source, "
 "is_shotgun, shotgun_quote, shotgun_source, data_type, data_quote, data_source, confidence. Booleans as true/false, or the string 'unsure'."
)

def _paper_block(r):
    ab = (r.abstractText or "").strip() or "(no abstract)"
    return f"### PAPER id={r.id}\nTITLE: {r.title}\nYEAR: {r.pubYear}  TYPES: {r.pubTypeList}\nABSTRACT: {ab}\n"

def _extract_json(text):
    text = text.strip()
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        return None
    s = m.group(0)
    try:
        return json.loads(s)
    except Exception:
        s2 = re.sub(r",\s*([\]}])", r"\1", s)
        try:
            return json.loads(s2)
        except Exception:
            return None

def _norm(v):
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("true", "yes"): return True
    if s in ("false", "no"): return False
    return "unsure"

def _rows_for(pid, obj, model, limited):
    """Build 4 validated rows for one paper."""
    vr = globals()["validate_row"]
    rows = []
    spec = [("is_human", "is_human", "human_quote", "human_source", _norm),
            ("has_infant_0_36m", "has_infant_0_36m", "infant_quote", "infant_source", _norm),
            ("is_shotgun", "is_shotgun", "shotgun_quote", "shotgun_source", _norm),
            ("data_type", "data_type", "data_quote", "data_source",
             lambda v: str(v).strip().lower() if str(v).strip().lower() in ("primary_new_data", "reanalysis_of_public_data", "review_or_method") else "unsure")]
    try:
        conf = float(obj.get("confidence", 0.5))
    except Exception:
        conf = 0.5
    conf = max(0.0, min(1.0, conf))
    for slot, vk, qk, sk, f in spec:
        val = f(obj.get(vk, "unsure"))
        q = str(obj.get(qk, "") or "").strip().strip('"').strip("'")
        src = str(obj.get(sk, "") or "").strip()
        if src not in ("paper.title", "paper.abstract"):
            src = "paper.abstract" if q else ""
        words = q.split()
        if len(words) > 12:
            q = " ".join(words[:12])
        row = {"record_id": pid, "slot": slot, "value": str(val), "outcome": "predicted",
               "confidence": round(min(conf, 0.6) if limited else conf, 3), "confidence_raw": round(conf, 3),
               "evidence": [{"source": src, "quote": q}] if q else [],
               "evidence_limited_to": "abstract" if limited else None, "model": model, "note": None}
        row["value_unanchored"] = None
        if not q:
            row["outcome"] = "sentinel_no_evidence"
            row["value_unanchored"] = str(val); row["value"] = None
            row["note"] = "no supporting quote returned"
        ok, msg = vr(row)
        if not ok:
            row["outcome"] = "validator_rejected"
            row["note"] = f"validate_row: {msg}"
        rows.append(row)
    return rows

def bind(h, vr):
    """Call once: SP.bind(host, validate_row)."""
    globals()["host"] = h; globals()["validate_row"] = vr

def screen(slice_path, prefix, model, start=0, stop=None, batch=20, concurrency=5, max_tokens=6000, limited_ids=None):
    df = pd.read_parquet(slice_path)
    if stop is None or stop > len(df):
        stop = len(df)
    df = df.iloc[start:stop]
    os.makedirs("ckpt", exist_ok=True); os.makedirs("tokens", exist_ok=True)
    reqs, groups = [], []
    for i in range(0, len(df), batch):
        g = df.iloc[i:i + batch]
        prompt = f"Screen these {len(g)} papers.\n\n" + "\n".join(_paper_block(r) for r in g.itertuples())
        reqs.append({"prompt": prompt, "system": SYSTEM, "model": model, "max_tokens": max_tokens, "temperature": 0})
        groups.append(g)
    t0 = time.time()
    res = host.llm(reqs, max_concurrency=concurrency)
    tok_in = tok_out = 0; n_err = 0; rows = []
    limited_ids = set(limited_ids or [])
    for g, r in zip(groups, res):
        if not isinstance(r, dict) or "error" in r or not r.get("text"):
            n_err += 1
            for pid in g.id:
                for s in SLOTS:
                    rows.append({"record_id": pid, "slot": s, "value": None, "outcome": "sentinel_no_evidence",
                                 "confidence": 0.0, "confidence_raw": None, "evidence": [], "evidence_limited_to": None,
                                 "model": model, "note": f"llm error: {str(r)[:200]}"})
            continue
        u = r.get("usage") or {}
        tok_in += int(u.get("input_tokens", 0)); tok_out += int(u.get("output_tokens", 0))
        arr = _extract_json(r["text"]) or []
        by_id = {str(o.get("id")): o for o in arr if isinstance(o, dict)}
        for pid in g.id:
            o = by_id.get(str(pid))
            if o is None:
                for s in SLOTS:
                    rows.append({"record_id": pid, "slot": s, "value": None, "outcome": "sentinel_no_evidence",
                                 "confidence": 0.0, "confidence_raw": None, "evidence": [], "evidence_limited_to": None,
                                 "model": model, "note": "paper missing from LLM response"})
            else:
                rows.extend(_rows_for(pid, o, model, pid in limited_ids))
    out = pd.DataFrame(rows)
    out["evidence"] = out["evidence"].apply(json.dumps)
    fn = f"ckpt/{prefix}_{start:05d}_{stop:05d}.parquet"
    out.to_parquet(fn, index=False)
    tk = {"job": f"{prefix}_{start}_{stop}", "model": model, "requests": len(reqs), "request_errors": n_err,
          "input_tokens": tok_in, "output_tokens": tok_out, "total_tokens": tok_in + tok_out, "seconds": round(time.time() - t0)}
    json.dump(tk, open(f"tokens/{prefix}_{start:05d}_{stop:05d}.json", "w"))
    print(fn, len(out), out.outcome.value_counts().to_dict(), tk)
    return fn, tk

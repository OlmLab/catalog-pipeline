"""Phase-2 driver around r3_prose_extract.run(): identical requests/prompts/model, but each (study, paper, chunk)
request is issued `n_rep` times (replicate tag in meta) and statements are unioned across replicates.
Everything else (JATS parse, chunking, statement validation, expansion) is delegated to r3_prose_extract."""
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
import json, time
import pandas as pd
import llm_batch_common as LBC
import r3_prose_extract as R3


def build_requests(studies, paper_sel, samples, r1det, conv, descs, unresolved, attrs, HL, system_text, papers_per_study=1, n_rep=2, skip_pairs=()):
    reqs, metas, nofull = [], [], []
    akeys = attrs.merge(samples[["sample_key", "study_accession"]]).groupby("study_accession").attr_key_norm.unique()
    for study in studies:
        pp = paper_sel[paper_sel.study_accession == study].head(papers_per_study)
        if pp.empty:
            nofull.append((study, None, "no_linked_paper"))
            continue
        ctx = R3.study_context(study, samples, r1det, conv, descs, unresolved, list(akeys.get(study, [])))
        for p in pp.itertuples(index=False):
            if (study, p.pmcid) in skip_pairs:
                continue
            r = HL.epmc_fulltext_xml(p.pmcid)
            if not r.get("ok"):
                nofull.append((study, p.pmcid, f"fulltext_http_{r.get('status')}")); continue
            secs = R3.jats_sections(r["body"])
            if not secs:
                nofull.append((study, p.pmcid, "jats_parse_failed")); continue
            for ci, ch in enumerate(R3.build_chunks(secs)):
                for rep in range(n_rep):
                    reqs.append(R3.build_request(ctx, p.relation, p.pmcid, ch, system_text))
                    metas.append({"ids": [f"{study}|{p.pmcid}|{ci}|r{rep}"], "slots": ["r3_statements"], "study": study, "pmcid": p.pmcid,
                                  "relation": p.relation, "chunk": ci, "rep": rep, "chars": len(ch)})
    return reqs, metas, nofull


def run_requests(reqs, metas, host, log_parquet, max_concurrency=4):
    LBC.HOST = host
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
            s = dict(s); s["_pmcid"] = meta["pmcid"]; s["_study"] = meta["study"]; s["_reused"] = meta["relation"] != "own_data"; s["_chunk"] = meta["chunk"]; s["_rep"] = meta["rep"]
            s["_relation"] = meta["relation"]
            v = str(s.get("value_normalized", "")).strip()
            s["value_normalized"] = v
            ok_v = R3._valid_value(s.get("field"), v)
            row = {"record_id": meta["study"], "slot": s.get("field"), "value": v, "value_unit": "days" if s.get("field") == "age_at_collection_days" else None,
                   "outcome": "predicted", "confidence": min(float(s.get("confidence", 0.5) or 0.5), 0.8), "model": R3.SONNET,
                   "evidence": [{"source": f"paper.fulltext.{s.get('section','methods')}", "quote": str(s.get("quote", ""))}],
                   "note": json.dumps(s.get("applies_to"))}
            if not ok_v:
                row["outcome"] = "validator_rejected"; row["note"] = f"validator_rejected: value '{v}' not in vocabulary for {s.get('field')}"
            s["_row"] = row
            all_statements.append(s)
            out.append(row)
        if not out:
            out.append(LBC.V["sentinel_row"](meta["study"], "r3_statements", R3.SONNET, note=f"no statements {meta['pmcid']} chunk {meta['chunk']} rep {meta['rep']}"))
        return out

    logdf, stats = LBC.run_batches(reqs, metas, make_rows, log_parquet, R3.SONNET, max_concurrency=max_concurrency)
    st_rows = []
    for s in all_statements:
        ok, msg = LBC.V["validate_row"](s["_row"])
        ok = ok and s["_row"]["outcome"] == "predicted"
        s["_valid"] = ok
        st_rows.append(dict(study_accession=s["_study"], pmcid=s["_pmcid"], relation=s["_relation"], reused=s["_reused"], chunk=s["_chunk"], replicate=s["_rep"],
                            field=s.get("field"), value_normalized=s["value_normalized"], value_raw=s.get("value_raw"), applies_to=json.dumps(s.get("applies_to")),
                            quote=s.get("quote"), section=s.get("section"), confidence=s.get("confidence"), note=s.get("note"), valid=ok,
                            reject_msg=None if ok else (msg or s["_row"].get("note"))))
    return pd.DataFrame(st_rows), all_statements, logdf, stats


def union_statements(all_statements):
    """Union across replicates: identical (study, pmcid, field, value, applies_to, quote-normalised) statements collapse to one,
    keeping the max confidence and recording in which replicates it appeared."""
    seen = {}
    for s in all_statements:
        if not s.get("_valid"):
            continue
        key = (s["_study"], s["_pmcid"], s.get("field"), s["value_normalized"], json.dumps(s.get("applies_to"), sort_keys=True), " ".join(str(s.get("quote", "")).lower().split()))
        if key in seen:
            seen[key]["_reps"].add(s["_rep"])
            seen[key]["confidence"] = max(float(seen[key].get("confidence", 0) or 0), float(s.get("confidence", 0) or 0))
        else:
            t = dict(s); t["_reps"] = {s["_rep"]}
            seen[key] = t
    return list(seen.values())


def expand_all(studies, uni, samples, r1det):
    dets = []
    for study in studies:
        ss = [s for s in uni if s["_study"] == study]
        if ss:
            d = R3.expand(ss, study, samples, r1det)
            if len(d):
                dets.append(d)
    return pd.concat(dets, ignore_index=True) if dets else pd.DataFrame()

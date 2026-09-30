"""Shared helpers for batched, validated LLM judgment jobs (infant catalog).

Usage inside a child kernel (environment=infantcat):
    # (sys.path handled by the repo layout shim above)
    from llm_batch_common import *
    load_validators(os.path.join(os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd(), "curation_kernel.py"))   # skill kernel.py copy -> validate_row etc. in module namespace
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
import json, time, math, os
import pandas as pd

V = {}   # validators namespace


def load_validators(path="curation_kernel.py"):
    ns = {}
    exec(open(path).read(), ns)
    V.update({k: ns[k] for k in ("validate_row", "validate_evidence", "validate_reason_code",
                                 "validate_age", "age_to_days", "sentinel_row", "find_accessions",
                                 "validate_accession_seen", "REASON_CODES", "SOURCE_PREFIXES", "OUTCOMES")
              if k in ns})
    return V


def tool_input(res):
    """Extract the tool_use input dict from a host.llm result (tolerant to shapes)."""
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
    # fallback: JSON in text
    t = res.get("text") or ""
    try:
        i, j = t.find("{"), t.rfind("}")
        return json.loads(t[i:j + 1]) if i >= 0 else None
    except Exception:
        return None


def usage_tokens(res):
    u = (res or {}).get("usage") or {}
    return int(u.get("input_tokens", 0) or 0) + int(u.get("output_tokens", 0) or 0)


HOST = None   # set by caller: llm_batch_common.HOST = host


def run_batches(requests, batch_meta, make_rows, out_parquet, model, max_concurrency=8,
                checkpoint_every=200, log_path=None):
    """requests: list of host.llm request dicts (already carrying model/tools/tool_choice).
    batch_meta: parallel list of per-batch metadata (e.g. list of record ids in that batch).
    make_rows(meta, parsed_input, res) -> list[row dict]; rows are validated here.
    Rows failing validate_row are kept with outcome='validator_rejected'.
    Returns (DataFrame, stats)."""
    host = HOST
    assert host is not None, "set llm_batch_common.HOST = host before calling run_batches"
    rows, stats = [], {"requests": len(requests), "tokens": 0, "errors": 0, "rejected": 0, "t0": time.time()}
    chunk = max(1, max_concurrency * 2)
    done_since_ckpt = 0
    for i in range(0, len(requests), chunk):
        reqs = requests[i:i + chunk]
        metas = batch_meta[i:i + chunk]
        results = host.llm(reqs, max_concurrency=max_concurrency)
        for meta, res in zip(metas, results):
            stats["tokens"] += usage_tokens(res)
            parsed = tool_input(res)
            if parsed is None:
                stats["errors"] += 1
                for rid in meta["ids"]:
                    for slot in meta.get("slots", ["verdict"]):
                        r = V["sentinel_row"](rid, slot, model, note="llm_error_or_unparsable")
                        r["outcome"] = "validator_rejected"
                        rows.append(r)
                continue
            for r in make_rows(meta, parsed, res):
                r.setdefault("model", model)
                ok, msg = V["validate_row"](r)
                if not ok:
                    stats["rejected"] += 1
                    r["note"] = f"validator_rejected: {msg}" + (f" | {r.get('note')}" if r.get("note") else "")
                    r["outcome"] = "validator_rejected"
                rows.append(r)
            done_since_ckpt += len(meta["ids"])
        if done_since_ckpt >= checkpoint_every:
            _write(rows, out_parquet)
            done_since_ckpt = 0
            print(f"[ckpt] {len(rows)} rows, {stats['tokens']:,} tok, {time.time()-stats['t0']:.0f}s", flush=True)
    df = _write(rows, out_parquet)
    stats["seconds"] = round(time.time() - stats["t0"])
    stats["rows"] = len(df)
    if log_path:
        json.dump(stats, open(log_path, "w"), indent=1)
    return df, stats


def _write(rows, path):
    df = pd.DataFrame(rows)
    if "evidence" in df:
        df["evidence"] = df["evidence"].apply(lambda e: json.dumps(e) if not isinstance(e, str) else e)
    df.to_parquet(path, index=False)
    return df

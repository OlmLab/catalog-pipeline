"""run_llm_shard.py — leaf-worker driver for the registry LLM classification stage (S1b).

    from catalog.registry.run_llm_shard import run_shard
    run_shard(host, universe_shard_parquet, det_parquet, out_prefix)

Reads one shard of registry_universe_studies (frozen columns), the deterministic classification rows (hints), runs
classify_llm.run_llm_stage (Sonnet ×2 → Opus adjudication; models from config/models.yaml roles) and writes
<out_prefix>.json (rows + cost) and <out_prefix>.parquet (registry-shaped rows). Every row returned is validated by
classify_llm (vocabularies, ≤12-word evidence, every id present; sentinels for failures). No literal model ids.
"""
from __future__ import annotations

import json
import os

import pandas as pd

from catalog.registry.build_registry import normalise_universe
from catalog.registry.classify_llm import run_llm_stage


def run_shard(host, universe_shard: str, det_path: str, out_prefix: str, max_concurrency: int = 8) -> pd.DataFrame:
    u = normalise_universe(pd.read_parquet(universe_shard))
    det = pd.read_parquet(det_path)
    det = det[det.study_accession.isin(set(u.study_accession))]
    dets = {r["study_accession"]: r for r in det.to_dict("records")}
    records = u.to_dict("records")
    os.makedirs(os.path.dirname(out_prefix) or ".", exist_ok=True)
    rows = run_llm_stage(records, dets, host, out_json=out_prefix + ".json", max_concurrency=max_concurrency,
                         log_path=out_prefix + "_cost.jsonl")
    df = pd.DataFrame(rows)
    df.to_parquet(out_prefix + ".parquet", index=False)
    cost = json.load(open(out_prefix + ".json")).get("cost", {})
    print(json.dumps({"n_in": len(u), "n_out": len(df), "stages": df.classification_stage.value_counts().to_dict() if "classification_stage" in df else {}, "cost": cost}))
    return df

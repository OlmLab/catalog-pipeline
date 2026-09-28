"""R2026.1 release notes generator: deterministic, sections present, numbers from the two packages (1.2.2 → 1.3.0 pair)."""
import json
import os
import shutil
import sys

import pandas as pd
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "src"))
from catalog.release import bitemporal as bt  # noqa: E402
from catalog.release import release_notes as rn  # noqa: E402

PKG = os.environ.get("CATALOG_PACKAGE_DIR", os.path.join(REPO, "data", "inputs", "data_package"))
SECTIONS = ["## Infant extension: studies and samples", "## Infant extension: per-field coverage on `catalog_scope`", "## Triage verdict flips", "## Findings applied",
            "## Sandpiper snapshot", "## Gold metrics", "## Schema changes", "## Token cost"]


def _mini(d, ver, flip=False, extra_sample=False):
    os.makedirs(d, exist_ok=True)
    keys = ["S1", "S2"] + (["S3"] if extra_sample else [])
    pd.DataFrame({"sample_key": keys, "catalog_scope": [True] * len(keys), "age_at_collection_days": [1.0, None] + ([3.0] if extra_sample else [])}).to_parquet(os.path.join(d, "sample_metadata_wide.parquet"), index=False)
    pd.DataFrame({"study_accession": ["PRJ1"]}).to_parquet(os.path.join(d, "study_metadata_wide.parquet"), index=False)
    pd.DataFrame({"study_accession": ["PRJ1", "PRJ2"], "triage_verdict": ["include", "include" if flip else "exclude"]}).to_parquet(os.path.join(d, "universe_studies_all.parquet"), index=False)
    pd.DataFrame({"field": ["age_at_collection_days"], "n_values_catalog_scope": [1]}).to_csv(os.path.join(d, "field_coverage_summary.csv"), index=False)
    pd.DataFrame({"gold_n": [10], "covered": [9], "correct": [9], "coverage": [0.9], "precision": [1.0], "recall": [0.9]}, index=pd.Index(["age_days"])).to_csv(os.path.join(d, "extraction_gold_eval_hires.csv"))
    json.dump({"package_version": ver, "build_date": "2026-09-26", "release_tag": f"data-v{ver}"}, open(os.path.join(d, "VERSION.json"), "w"))


def test_synthetic_pair_sections_and_flip(tmp_path):
    a, b = str(tmp_path / "a"), str(tmp_path / "b")
    _mini(a, "1.2.2")
    _mini(b, "1.3.0", flip=True, extra_sample=True)
    md = rn.build(a, b, cycle_log=str(tmp_path / "none.md"))
    assert md.startswith("# Release notes — R2026.1 (data package 1.3.0, 2026-09-26)")
    for s in SECTIONS:
        assert s in md, s
    assert "| catalog samples | 2 | 3 | 1 | 0 |" in md
    assert "**1 flips**" in md and "| PRJ2 | exclude | include |" in md
    assert "| `age_at_collection_days` | 1 | 50.0% | 2 | 66.7% | +1 |" in md
    assert "LLM tokens this cycle: not recorded" in md
    assert md == rn.build(a, b, cycle_log=str(tmp_path / "none.md"))  # deterministic


def test_cycle_log_row_is_read(tmp_path):
    p = tmp_path / "CYCLE_LOG.md"
    p.write_text("| cycle | date | SINCE | cand | includes | tokens | wall |\n|---|---|---|---|---|---|---|\n| R2026.1 | 2026-09-26 | — | 0 | 389 | 0 (deterministic) | 3 h |\n")
    assert rn.cycle_log_line("R2026.1", "1.3.0", str(p)) == "0 (deterministic) (docs/CYCLE_LOG.md row `R2026.1`)"
    assert rn.cycle_log_line("R2027.1", "1.4.0", str(p)) == "not recorded"


@pytest.mark.skipif(not os.path.exists(os.path.join(PKG, "sample_determinations.parquet")), reason="no unpacked package")
def test_real_pair_1_2_2_to_1_3_0(tmp_path):
    """From a 1.2.2 package: reconstruction to R2026.1. From a 1.3.0 (bitemporal) package: incremental to R2026.2 (R2026.2 test)."""
    import pyarrow.parquet as pq
    out = str(tmp_path / "new")
    incremental = "release_added" in pq.ParquetFile(os.path.join(PKG, "sample_determinations.parquet")).schema_arrow.names
    if incremental:
        pv = json.load(open(os.path.join(PKG, "VERSION.json"))).get("package_version", "")
        if tuple(int(x) for x in pv.split(".")) > (1, 4, 0):
            pytest.skip(f"pinned to the 1.2.2→1.3.0 / 1.3.0→1.4.0 pairs (PKG_SRC is {pv}: gap-fill changed the sample count)")
    rid, pv, prev = ("R2026.2", "1.4.0", "1.3.0") if incremental else ("R2026.1", "1.3.0", "1.2.2")
    bt.run(PKG, out, rid, pv, prev, previous_package=PKG, release_date="2026-09-26")
    v = json.load(open(os.path.join(PKG, "VERSION.json")))
    v.update(package_version=pv, release_id=rid, previous_release_id=("R2026.1" if incremental else "1.2.2"), release_tag=f"data-v{pv}")
    json.dump(v, open(os.path.join(out, "VERSION.json"), "w"))
    md = rn.build(PKG, out)
    assert "| included studies | 389 | 389 | 0 | 0 |" in md
    assert "| catalog samples | 154,206 | 154,206 | 0 | 0 |" in md
    assert "**0 flips**" in md
    if not incremental:
        assert "New files: `bitemporal_log.json`, `releases.csv`, `sample_determinations_all.parquet`" in md
    assert "| 1.0.0 | 605,707 |" in md and "| 1.2.2 | 701 |" in md
    assert "| sandpiper_version | 2.0.0 | 2.0.0 |" in md
    assert md == rn.build(PKG, out)

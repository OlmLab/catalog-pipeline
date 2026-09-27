"""apply_verdicts.py — append validated triage verdicts for NEW studies (re-sweep candidates judged in the cycle) to the
package's universe_studies_all.parquet and study_verdict_history.parquet (RUNBOOK stage 2 → 5).

    python -m catalog.triage.apply_verdicts --package build/package --verdicts build/resweep_<cycle>/verdicts.parquet \
        --stage resweep_2026-09b_session_review --date 2026-09-27

Verdict rows carry: record_id (study accession), value (include|exclude|uncertain), outcome, confidence, reason_code,
evidence (json list of {source, quote}), model, note, study_title, n_samples, n_runs, first_public_min, decision_stage,
universe_slice, validator_ok. Rows whose validator_ok is False are refused. Existing studies are never overwritten
(a changed verdict for an existing study is a finding, not a verdict row). The release columns are left to
catalog.release.bitemporal (incremental mode: new keys → the current release id).
"""
from __future__ import annotations

import argparse
import json
import os

import pandas as pd

UNIVERSE = "universe_studies_all.parquet"
HISTORY = "study_verdict_history.parquet"


def run(package: str, verdicts: str, stage: str, date: str) -> dict:
    v = pd.read_parquet(verdicts)
    assert v["validator_ok"].all(), "refusing verdict rows that failed the curation validators"
    u = pd.read_parquet(os.path.join(package, UNIVERSE))
    h = pd.read_parquet(os.path.join(package, HISTORY))
    dup = set(v.record_id) & set(u.study_accession)
    assert not dup, f"verdicts for studies already in the universe (file a finding instead): {sorted(dup)}"
    rows = []
    for r in v.itertuples(index=False):
        row = {c: None for c in u.columns if c not in ("release_added", "release_retired", "package_added")}
        row.update(study_accession=r.record_id, triage_verdict=r.value, outcome=r.outcome, confidence=float(r.confidence),
                   reason_code=r.reason_code, evidence=r.evidence, model=r.model, decision_stage=getattr(r, "decision_stage", stage) or stage,
                   note=r.note, slot="triage_verdict", validator_ok=bool(r.validator_ok), validator_msg="",
                   study_title=getattr(r, "study_title", None), n_samples=getattr(r, "n_samples", None), n_runs=getattr(r, "n_runs", None),
                   first_public_min=getattr(r, "first_public_min", None), universe_slice=getattr(r, "universe_slice", None),
                   catalog_status="excluded" if r.value == "exclude" else ("included" if r.value == "include" else "human_review"))
        rows.append(row)
    new_u = pd.DataFrame(rows)
    for c in u.columns:
        if c not in new_u.columns:
            new_u[c] = None
    new_u = new_u[[c for c in u.columns]]
    for c in u.columns:  # keep dtypes stable where possible
        try:
            new_u[c] = new_u[c].astype(u[c].dtype)
        except Exception:  # noqa: BLE001 — object fallback
            pass
    hist_rows = [dict(study_accession=r.record_id, stage_order=1, stage=stage, stage_family="cycle_resweep", stage_table=os.path.basename(verdicts),
                      replicate=None, verdict=r.value, verdict_norm=r.value, outcome=r.outcome, confidence=float(r.confidence), model=r.model,
                      reason_code=r.reason_code, evidence=r.evidence, n_infant_samples_est=0.0, note=r.note, validator_ok=bool(r.validator_ok),
                      is_final=True, date=pd.Timestamp(date), src_artifact=os.path.basename(verdicts), src_version_id=None, stage_rank=95000,
                      stage_level="cycle_resweep", is_consolidated=True, consolidated_kind="cycle_resweep", verdict_norm_note=None) for r in v.itertuples(index=False)]
    new_h = pd.DataFrame(hist_rows)
    for c in h.columns:
        if c not in new_h.columns:
            new_h[c] = None
    new_h = new_h[list(h.columns)]
    pd.concat([u, new_u], ignore_index=True).to_parquet(os.path.join(package, UNIVERSE), index=False)
    pd.concat([h, new_h], ignore_index=True).to_parquet(os.path.join(package, HISTORY), index=False)
    log = {"n_verdicts": int(len(v)), "verdicts": v.value.value_counts().to_dict(), "universe_rows": int(len(u) + len(new_u)), "history_rows": int(len(h) + len(new_h)), "stage": stage}
    print(json.dumps(log))
    return log


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", required=True)
    ap.add_argument("--verdicts", required=True)
    ap.add_argument("--stage", required=True)
    ap.add_argument("--date", required=True)
    a = ap.parse_args(argv)
    run(a.package, a.verdicts, a.stage, a.date)


if __name__ == "__main__":
    main()

#!/usr/bin/env python
"""apply_findings.py — apply auditor / human findings to the catalog tables (Reviewer A finding A10).

Findings arrive as CSV rows in ``audit/findings/*.csv`` (schema = auditor_findings.csv, written by the
read-only Auditor session or by the GitHub Issue template ``.github/ISSUE_TEMPLATE/catalog-finding.yml``):

    date, identifier, finding_type, current_state, proposed_change, evidence_quote, evidence_source,
    confidence
  + structured columns that make a finding machine-applicable (all optional; free-text-only rows are
    reported under "needs_structuring" and are never applied):
    action        add_determination | supersede_determination | study_verdict | study_note | paper_link | note_only |
                  confirm (F2: truth-set row → confirmations.parquet + <field>__verified in the wide table) | add_study
                  (universe_miss → candidates_<date>.csv for the next triage cycle). Vocabulary = audit/schema.json.
    sample_key    catalog sample key (SAMN…/SAMEA…/SAMD… or run accession for run-keyed units)
    field_name    one of the determination fields (age_at_collection_days, delivery_mode, …)
    new_value     the value to commit (already normalised; ages in days)
    route         R1 | R2 | R3 | R4 | H (H = human/external curation; DEFAULT for external_curation.* sources, R1-06)
    reason_code   for study_verdict exclusions (controlled vocabulary, kernel REASON_CODES)
    source        GitHub issue number or session id (recorded in src_track)

Every applicable row is re-validated with the skill validators (curation_kernel_ext.validate_row:
source-label prefixes, ≤12-word quote, age range, reason code, extension vocabularies) BEFORE any table
is touched. Rows failing validation are written to the report with the validator message and skipped —
they are never silently downgraded (Rule 7).

Applied rows carry ``decision_stage='auditor_review'`` and ``src_track='auditor_review:<source>'``.
Superseded rows move to ``sample_determinations_superseded.parquet`` with ``superseded_by='auditor_review'``.
The script writes ``<out>/APPLY_FINDINGS_DIFF.md`` and never edits tables in place: outputs go to ``--out``.
Tables are emitted ONLY when ≥ 1 row has status applied (then ``<out>/APPLIED`` exists and `make package` copies them);
R1-06: sample_metadata_wide / universe_studies_all are rewritten in step (``rewide``) so long and wide tables agree.

Usage:
    python -m catalog.apply_findings --package data/package --findings audit/findings --out build/applied
    python -m catalog.apply_findings ... --dry-run          # validate + diff only
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import importlib.util
import json
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from catalog import findings_schema as FS  # noqa: E402  — audit/schema.json is the single source (R1-09/F2)

SCHEMA = FS.load()
FINDING_COLS = FS.finding_cols(SCHEMA)
STRUCT_COLS = FS.struct_cols(SCHEMA)
DET_COLS = ["sample_key", "field_name", "study_accession", "field_value", "value_normalized", "confidence",
            "evidence_source", "evidence_locator", "evidence_quote", "evidence_limited_to_abstract",
            "determined_by", "route", "scope", "parse_note", "group_audit", "src_track"]
ACTIONS = FS.actions(SCHEMA)
FINDING_TYPES = set(FS.finding_types(SCHEMA))
EVIDENCE_OPTIONAL_TYPES = set(SCHEMA["issue_form"]["evidence_optional_for"])
CONFIRM_COLS = ["date", "identifier", "sample_key", "field_name", "confirmed_value", "confirmed_by", "source", "release_tag", "note"]
AGE_FIELDS = {"age_at_collection_days": ("days", 0, 1100), "gestational_age_weeks": ("weeks", 20, 45)}


def load_kernel():
    """Import the repo copy of the validators (identical to the skill kernel; tests/test_validators_sync.py)."""
    path = os.path.join(HERE, "triage", "curation_kernel_ext.py")
    spec = importlib.util.spec_from_file_location("curation_kernel_ext", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_findings(findings_dir: str) -> pd.DataFrame:
    files = sorted(glob.glob(os.path.join(findings_dir, "*.csv")))
    if not files:
        raise SystemExit(f"no findings CSV under {findings_dir}")
    parts = []
    for f in files:
        df = pd.read_csv(f, dtype=str, keep_default_na=False)
        missing = [c for c in FINDING_COLS if c not in df.columns]
        if missing:
            raise SystemExit(f"{f}: missing required columns {missing}")
        for c in STRUCT_COLS:
            if c not in df.columns:
                df[c] = ""
        df["_file"] = os.path.basename(f)
        df["_row"] = range(len(df))
        parts.append(df)
    return pd.concat(parts, ignore_index=True)


def quote_words(q: str) -> int:
    return len(str(q).split())


def validate_finding(row: pd.Series, K, det: pd.DataFrame, studies: pd.DataFrame, all_samples: set = frozenset()) -> tuple[bool, str]:
    """Return (ok, message). Uses the kernel validators; adds table-consistency checks."""
    action = row["action"].strip()
    if not action:
        return False, "needs_structuring: no `action` column value (free-text finding)"
    if action not in ACTIONS:
        return False, f"unknown action {action!r} (audit/schema.json actions: {sorted(ACTIONS)})"
    ft = row["finding_type"].strip()
    if ft and ft not in FINDING_TYPES:
        return False, f"unknown finding_type {ft!r} (audit/schema.json)"
    if ft and action not in SCHEMA["finding_types"][ft]["actions"]:
        return False, f"action {action!r} not allowed for finding_type {ft!r} (allowed: {SCHEMA['finding_types'][ft]['actions']})"
    if action == "note_only":
        return True, "note only — recorded, nothing applied"
    if action == "add_study":
        return True, "candidate recorded for the next triage cycle (never a direct include)"
    if action == "confirm":
        # F2: a confirmation is a truth-set row; evidence quote/confidence are optional. Sample-level needs an existing cell.
        if row["sample_key"]:
            if not row["field_name"]:
                return False, "confirm with sample_key needs field_name"
            if row["sample_key"] not in all_samples and row["sample_key"] not in det["sample_key"].values:
                return False, f"sample_key {row['sample_key']} not in sample table"
            cur = det[(det.sample_key == row["sample_key"]) & (det.field_name == row["field_name"])]
            if cur.empty:
                return False, "confirm: no current determination for that sample_key/field_name"
        elif row["identifier"] not in studies["study_accession"].values:
            return False, f"study {row['identifier']} not in study table"
        return True, "ok"
    src = row["evidence_source"].strip()
    # human / auditor evidence must be labelled with an allowed source prefix; GitHub-issue findings use
    # external_curation.human (skill kernel SOURCE_PREFIXES include "external_curation.")
    ev = [{"source": src, "quote": row["evidence_quote"].strip()}]
    ok, msg = K.validate_evidence(ev)
    if not ok:
        return False, f"validate_evidence: {msg}"
    if quote_words(row["evidence_quote"]) > 12:
        return False, "quote > 12 words"
    try:
        conf = float(row["confidence"])
    except ValueError:
        return False, "confidence not numeric"
    if not 0 <= conf <= 1:
        return False, "confidence outside 0–1"
    if action in ("add_determination", "supersede_determination"):
        if not row["sample_key"] or not row["field_name"] or row["new_value"] == "":
            return False, "add/supersede needs sample_key, field_name, new_value"
        if row["field_name"] in AGE_FIELDS:
            unit, lo, hi = AGE_FIELDS[row["field_name"]]
            ok, msg, _days = K.validate_age(row["new_value"], unit)
            if not ok:
                return False, f"validate_age: {msg}"
        if row["sample_key"] not in all_samples and row["sample_key"] not in det["sample_key"].values:
            return False, f"sample_key {row['sample_key']} not in sample table"
        if action == "supersede_determination":
            cur = det[(det.sample_key == row["sample_key"]) & (det.field_name == row["field_name"])]
            if cur.empty:
                return False, "supersede requested but no current determination exists (use add_determination)"
        kernel_row = dict(record_id=row["sample_key"], slot=row["field_name"], value=row["new_value"],
                          outcome="resolved_from_raw", confidence=conf, evidence=ev, model="human")
        ok, msg = K.validate_row(kernel_row)
        if not ok:
            return False, f"validate_row: {msg}"
    elif action == "study_verdict":
        if row["identifier"] not in studies["study_accession"].values:
            return False, f"study {row['identifier']} not in study table"
        if row["new_value"] not in ("included", "excluded", "human_review"):
            return False, "study_verdict new_value must be included|excluded|human_review"
        if row["new_value"] == "excluded":
            ok, msg = K.validate_reason_code(row["reason_code"])
            if not ok:
                return False, f"validate_reason_code: {msg}"
    elif action in ("study_note", "paper_link"):
        if row["identifier"] not in studies["study_accession"].values:
            return False, f"study {row['identifier']} not in study table"
    return True, "ok"


def apply(findings: pd.DataFrame, det: pd.DataFrame, sup: pd.DataFrame, studies: pd.DataFrame, samples: pd.DataFrame,
          K, today: str):
    det = det.copy()
    if "decision_stage" not in det.columns:
        det["decision_stage"] = pd.NA
    sup = sup.copy()
    studies = studies.copy()
    if "decision_stage" not in studies.columns:
        studies["decision_stage"] = pd.NA
    all_samples = set(samples["sample_key"]) if samples is not None else set()
    log = []
    new_rows, moved, confirmations, candidates = [], [], [], []
    for _, r in findings.iterrows():
        ok, msg = validate_finding(r, K, det, studies, all_samples)
        entry = dict(file=r["_file"], row=int(r["_row"]), identifier=r["identifier"], action=r["action"],
                     finding_type=r["finding_type"], sample_key=r["sample_key"], field_name=r["field_name"],
                     new_value=r["new_value"], status="", message=msg)
        if not ok:
            entry["status"] = "rejected" if not msg.startswith("needs_structuring") else "needs_structuring"
            log.append(entry)
            continue
        act = r["action"]
        src_track = f"auditor_review:{r['source'] or r['_file']}"
        if act in ("add_determination", "supersede_determination"):
            study_acc = r["identifier"] if str(r["identifier"]).startswith("PRJ") else ""
            if not study_acc and samples is not None:
                m = samples.loc[samples.sample_key == r["sample_key"], "study_accession"]
                study_acc = m.iloc[0] if len(m) else ""
            if act == "supersede_determination":
                mask = (det.sample_key == r["sample_key"]) & (det.field_name == r["field_name"])
                old = det[mask].copy()
                old["superseded_by"] = "auditor_review"
                old["superseded_reason"] = f"{r['finding_type']}: {r['proposed_change'][:200]}"
                moved.append(old)
                det = det[~mask]
            # R1-06: route defaults to H (human / external curation) for external_curation.* sources, never R2
            route = r["route"] or ("H" if r["evidence_source"].startswith("external_curation.") else "R2")
            new_rows.append(dict(sample_key=r["sample_key"], field_name=r["field_name"], study_accession=study_acc,
                                 field_value=r["new_value"], value_normalized=r["new_value"], confidence=float(r["confidence"]),
                                 evidence_source=r["evidence_source"], evidence_locator=r["evidence_source"],
                                 evidence_quote=r["evidence_quote"], evidence_limited_to_abstract=0.0,
                                 determined_by="auditor_review", route=route, scope="sample",
                                 parse_note=f"{r['finding_type']}; {r['date']}", group_audit=pd.NA,
                                 src_track=src_track, decision_stage="auditor_review"))
            entry["status"] = "applied"
        elif act == "study_verdict":
            m = studies.study_accession == r["identifier"]
            prev = studies.loc[m, "catalog_status"].iloc[0] if "catalog_status" in studies else ""
            studies.loc[m, "catalog_status"] = r["new_value"]
            if r["reason_code"]:
                studies.loc[m, "reason_code"] = r["reason_code"]
            studies.loc[m, "decision_stage"] = "auditor_review"
            studies.loc[m, "note"] = (studies.loc[m, "note"].fillna("").astype(str) +
                                      f" | auditor_review {r['date']}: {prev}→{r['new_value']}; {r['evidence_quote']}")
            entry["status"] = "applied"
            entry["message"] = f"{prev} -> {r['new_value']}"
        elif act == "confirm":
            cur_val = ""
            if r["sample_key"]:
                cur = det[(det.sample_key == r["sample_key"]) & (det.field_name == r["field_name"])]
                cur_val = str(cur["value_normalized"].iloc[0]) if len(cur) else ""
            confirmations.append(dict(date=r["date"], identifier=r["identifier"], sample_key=r["sample_key"], field_name=r["field_name"],
                                      confirmed_value=cur_val, confirmed_by="human", source=r["source"] or r["_file"],
                                      release_tag=r.get("release_tag", ""), note=r["proposed_change"][:300]))
            entry["status"] = "applied"
            entry["message"] = f"confirmed {cur_val!r}" if cur_val else "study-level confirmation recorded"
        elif act == "add_study":
            candidates.append(dict(date=r["date"], study_accession=r["identifier"], proposed_change=r["proposed_change"][:500],
                                   evidence_quote=r["evidence_quote"], evidence_source=r["evidence_source"], source=r["source"] or r["_file"]))
            entry["status"] = "recorded"
        elif act in ("study_note", "paper_link"):
            m = studies.study_accession == r["identifier"]
            studies.loc[m, "note"] = (studies.loc[m, "note"].fillna("").astype(str) +
                                      f" | auditor_review {r['date']} [{act}]: {r['proposed_change'][:300]}")
            studies.loc[m, "decision_stage"] = "auditor_review"
            entry["status"] = "applied" if act == "study_note" else "applied_as_note (paper_link rows need link_papers.py re-run)"
        else:
            entry["status"] = "recorded"
        log.append(entry)
    if new_rows:
        det = pd.concat([det, pd.DataFrame(new_rows)], ignore_index=True)
    if moved:
        sup = pd.concat([sup] + moved, ignore_index=True)
    conf_df = pd.DataFrame(confirmations, columns=CONFIRM_COLS)
    cand_df = pd.DataFrame(candidates, columns=["date", "study_accession", "proposed_change", "evidence_quote", "evidence_source", "source"])
    return det, sup, studies, pd.DataFrame(log), conf_df, cand_df


def rewide(wide: pd.DataFrame, det: pd.DataFrame, conf: pd.DataFrame, studies: pd.DataFrame, universe: pd.DataFrame | None,
           applied_log: pd.DataFrame):
    """R1-06: bring the WIDE tables in line with the long tables after apply().

    * every applied add/supersede row → sample_metadata_wide[<field>, <field>__confidence, <field>__route] for that sample
      (incremental — build_wide.py needs the sample/subject/run frames that are not in the package);
    * every sample-level confirmation → sample_metadata_wide[<field>__verified] = True (F2);
    * study_verdict → universe_studies_all.catalog_status/decision_stage; samples of a study that is now `excluded` leave
      sample_metadata_wide (moved to sample_metadata_wide_excluded_by_review.parquet) so the explorer/study lists agree.
    Returns (wide, universe, excluded_rows, n_cells).
    """
    wide = wide.copy()
    n_cells = 0
    touched = applied_log[(applied_log.status == "applied") & applied_log.action.isin(["add_determination", "supersede_determination"])]
    idx = wide.set_index("sample_key").index
    for _, t in touched.iterrows():
        cur = det[(det.sample_key == t.sample_key) & (det.field_name == t.field_name)]
        if cur.empty or t.sample_key not in idx:
            continue
        row = cur.iloc[-1]
        pos = wide.index[wide.sample_key == t.sample_key]
        for col, val in ((t.field_name, row["value_normalized"]), (f"{t.field_name}__confidence", row["confidence"]), (f"{t.field_name}__route", row["route"])):
            if col not in wide.columns:
                wide[col] = pd.NA
            if col == t.field_name and pd.api.types.is_numeric_dtype(wide[col]):
                val = pd.to_numeric(val, errors="coerce")
            wide.loc[pos, col] = val
        n_cells += 1
    for _, c in conf[conf.sample_key.astype(str) != ""].iterrows():
        col = f"{c.field_name}__verified"
        if col not in wide.columns:
            wide[col] = False
        wide.loc[wide.sample_key == c.sample_key, col] = True
    excluded = []
    verdicts = applied_log[(applied_log.status == "applied") & (applied_log.action == "study_verdict")]
    for _, v in verdicts.iterrows():
        st = studies.loc[studies.study_accession == v.identifier]
        if st.empty:
            continue
        status = st["catalog_status"].iloc[0]
        if universe is not None and "catalog_status" in universe.columns:
            um = universe.study_accession == v.identifier
            universe.loc[um, "catalog_status"] = status
            if "decision_stage" in universe.columns:
                universe.loc[um, "decision_stage"] = "auditor_review"
        if status == "excluded":
            m = wide.study_accession == v.identifier
            excluded.append(wide[m])
            wide = wide[~m]
    exc = pd.concat(excluded, ignore_index=True) if excluded else wide.iloc[0:0]
    return wide, universe, exc, n_cells


def write_diff(log: pd.DataFrame, before: dict, after: dict, out: str, dry: bool):
    lines = [f"# APPLY_FINDINGS diff — {dt.date.today().isoformat()}{' (DRY RUN)' if dry else ''}", ""]
    lines.append("| status | n |\n|---|---|")
    for s, n in log["status"].value_counts().items():
        lines.append(f"| {s} | {n} |")
    lines += ["", "| table | rows before | rows after |", "|---|---|---|"]
    for k in before:
        lines.append(f"| {k} | {before[k]} | {after[k]} |")
    lines += ["", "## Per-finding log", "", "| file | row | identifier | action | field | new_value | status | message |", "|---|---|---|---|---|---|---|---|"]
    for _, r in log.iterrows():
        lines.append(f"| {r.file} | {r.row} | {r.identifier} | {r.action} | {r.field_name} | {r.new_value} | {r.status} | {str(r.message).replace('|', '/')} |")
    open(os.path.join(out, "APPLY_FINDINGS_DIFF.md"), "w").write("\n".join(lines) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--package", required=True, help="unzipped data package dir (sample_determinations.parquet, …)")
    ap.add_argument("--findings", default="audit/findings")
    ap.add_argument("--out", default="build/applied")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    K = load_kernel()
    P = lambda n: os.path.join(a.package, n)
    det = pd.read_parquet(P("sample_determinations.parquet"))
    sup = pd.read_parquet(P("sample_determinations_superseded.parquet")) if os.path.exists(P("sample_determinations_superseded.parquet")) else pd.DataFrame(columns=DET_COLS + ["superseded_by", "superseded_reason"])
    studies = pd.read_parquet(P("study_metadata_wide.parquet"))
    samples = pd.read_parquet(P("sample_metadata_wide.parquet"), columns=["sample_key", "study_accession"]) if os.path.exists(P("sample_metadata_wide.parquet")) else None
    findings = read_findings(a.findings)
    before = dict(sample_determinations=len(det), superseded=len(sup), studies=len(studies))
    det2, sup2, st2, log, conf, cand = apply(findings, det, sup, studies, samples, K, dt.date.today().isoformat())
    after = dict(sample_determinations=len(det2), superseded=len(sup2), studies=len(st2))
    log.to_csv(os.path.join(a.out, "apply_findings_log.csv"), index=False)
    n_applied = int((log["status"] == "applied").sum()) if len(log) else 0
    write_diff(log, before, after, a.out, a.dry_run)
    marker = os.path.join(a.out, "APPLIED")
    if os.path.exists(marker):
        os.remove(marker)
    if len(cand):
        cand.to_csv(os.path.join(a.out, f"candidates_{dt.date.today().isoformat()}.csv"), index=False)
    # R1-06: emit tables ONLY when at least one row was applied — a no-op run must not produce byte-different copies
    if not a.dry_run and n_applied:
        wide_full = pd.read_parquet(P("sample_metadata_wide.parquet"))
        universe = pd.read_parquet(P("universe_studies_all.parquet")) if os.path.exists(P("universe_studies_all.parquet")) else None
        wide2, uni2, exc, n_cells = rewide(wide_full, det2, conf, st2, universe, log)
        det2.to_parquet(os.path.join(a.out, "sample_determinations.parquet"), index=False)
        sup2.to_parquet(os.path.join(a.out, "sample_determinations_superseded.parquet"), index=False)
        st2.to_parquet(os.path.join(a.out, "study_metadata_wide.parquet"), index=False)
        st2.to_csv(os.path.join(a.out, "study_metadata_wide.csv"), index=False)
        wide2.to_parquet(os.path.join(a.out, "sample_metadata_wide.parquet"), index=False, compression="zstd")
        if uni2 is not None:
            uni2.to_parquet(os.path.join(a.out, "universe_studies_all.parquet"), index=False)
        if len(exc):
            exc.to_parquet(os.path.join(a.out, "sample_metadata_wide_excluded_by_review.parquet"), index=False)
        prev_conf = P("confirmations.parquet")
        if os.path.exists(prev_conf):
            conf = pd.concat([pd.read_parquet(prev_conf), conf], ignore_index=True)
        conf.to_parquet(os.path.join(a.out, "confirmations.parquet"), index=False)
        open(marker, "w").write(f"{n_applied} applied; {n_cells} wide cells rewritten; {len(exc)} sample rows left the wide table\n")
        after.update(wide_cells_rewritten=n_cells, wide_rows_excluded=int(len(exc)), confirmations=int(len(conf)))
    print(json.dumps(dict(before=before, after=after, n_applied=n_applied, statuses=log["status"].value_counts().to_dict())))
    return 0


if __name__ == "__main__":
    sys.exit(main())

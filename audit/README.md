# audit/findings/

One CSV per finding batch, named `YYYY-MM-DD_<source>.csv` (source = `auditor_session`, `issues`, `human_review`…).
Schema = auditor_findings.csv (date, identifier, finding_type, current_state, proposed_change, evidence_quote,
evidence_source, confidence) + the structured columns `action, sample_key, field_name, new_value, route, reason_code,
source` that make a row machine-applicable (see `src/catalog/apply_findings.py`). Rows without `action` are reported
as `needs_structuring` and never applied. `2026-09-25_auditor_session.csv` is the first batch (3 findings, already
applied by hand in release v11 — kept as the schema example; running apply_findings on it is a no-op because it has
no `action` column).

## Schema, Issues and confirmations (R1-09 / F2, 2026-09-26)

* `audit/schema.json` is the single source: CSV columns, finding_type → allowed actions, action → required fields,
  routes (incl. `H`), field names, reason codes. `python -m catalog.findings_schema --write-template` regenerates the
  GitHub issue form; `--check` fails when the form drifted; `--auditor-vocab` prints the Auditor's finding_type list.
* `make ingest-issues` → `audit/findings/YYYY-MM-DD_issues.csv` (`src/catalog/ingest_issues.py`; `date`/`source` come
  from the Issue, never typed by hand; already-ingested `issue#N` sources are skipped).
* `action = confirm` → `confirmations.parquet` (date, identifier, sample_key, field_name, confirmed_value, source) and
  `<field>__verified` on the wide table; `action = add_study` → `candidates_<date>.csv` for the next triage cycle.
* Applied outputs land in `build/applied_<package_version>/` only when ≥ 1 row applied (`APPLIED` marker); the wide
  tables are rewritten in step so long and wide never disagree (R1-06).

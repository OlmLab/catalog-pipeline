# src/catalog/sandpiper — Sandpiper taxonomy module (R3-4, R1-14)

Vendored 2026-09-26 from the artifacts that produced the shipped `sandpiper_*` tables (ids + sha256 in `config/inputs.json`,
group `code`). The scripts keep their original flat `sp/` working-directory convention: every Make target `cd`s into
`build/sandpiper_<ZENODO_RECORD>/` and the scripts read/write `sp/*` relative to it.

| step | script | reads | writes | runtime / requests (2026-09 build) |
|---|---|---|---|---|
| 1 | `download_bulk.py` | Zenodo record `$SANDPIPER_ZENODO_RECORD` (default 20419175), file `sandpiper<ver>.gtdb.csv.gz` | `sp/sandpiper<ver>.gtdb.csv.gz` (3.7 GB), `sp/download_log.json` (sha256, md5 vs Zenodo) | 29 min, 1 request (resumable) |
| 2 | `prepare_inputs.py` | `catalog_runs_sandpiper_match.parquet`, `per_acc_summary.csv.gz`, package wide table + `runs.parquet` | `sp/matched_runs.parquet`, `sp/sample_run_totals.parquet`, `sp/sample_scope.parquet`, `sp/run_qc_input.parquet` | ≈ 2 min, 0 requests — **reconstruction**, see its docstring |
| 3 | `filter_bulk.py` | bulk file + `sp/matched_runs.parquet` | `sp/sandpiper_profiles_runs_raw.parquet` | ≈ 25 min single pass |
| 4 | `build_sandpiper_tables.py` (+ `sandpiper_lib.py`) | step 2–3 outputs | `sp/sandpiper_*.parquet/csv`, `sp/build_log.json` | ≈ 10 min, DuckDB 8 threads / 24 GB |
| 5 | `render_report.py` | `handoff/report_numbers.json`, `sp/build_log.json` | `sp/SANDPIPER_REPORT.md` | seconds |

`make sandpiper-refresh ZENODO_RECORD=<id> SANDPIPER_VERSION=<x.y.z>` runs 1–5 for a NEW Zenodo version (RUNBOOK stage 1c).
`make sandpiper-delta` (RUNBOOK stage 1b, Curator) runs 2–4 against the CURRENT snapshot for runs added since the last
package — no download; the bulk snapshot comes from `~/catalog/external/sandpiper/<version>/` or the snapshot artifact
(`config/inputs.json` → `sandpiper2.0.0.gtdb.csv.gz`, artifact 8071e8b8, sha256 4732c4e1…).
`catalog_runs_sandpiper_match.parquet` must be re-derived when new runs enter the catalog (membership = run accession present
in `per_acc_summary`); `prepare_inputs.py` takes the refreshed match table.

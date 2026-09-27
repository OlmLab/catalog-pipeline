# RELEASES — the catalog release model (MATURITY_PLAN §2, implemented in R2026.1)

Machine-readable twin: `config/releases.yaml` (the ONLY place ids, column names, table lists and page paths are
defined; `bitemporal.py`, `release_notes.py`, `make_version.py` and the site generator all read it).

## 1. Identifiers

| thing | form | example | where |
|---|---|---|---|
| numbered catalog release | `R<YYYY>.<n>` (regex `^R\d{4}\.\d+$`) | `R2026.1` | `releases.csv`, `VERSION.json.release_id`, release-column values |
| data package format | semver | `1.3.0` | `config/version.txt`, `VERSION.json.package_version`, `package_added` |
| git tags | `data-v<semver>` / `site-v<semver>` | `data-v1.3.0` | data repo Release / Pages deploy |
| pre-numbered historical state | the package semver that shipped it | `1.2.2` | release-column values only |

The first numbered release is **R2026.1 = package 1.3.0**. Everything published before it is identified by its
package semver: `1.0.0` (first public package, package CHANGELOG "v1", bundle v10, 2026-09-25), `1.1.0` (release v11,
sample-unit fix, 2026-09-25), `1.2.0` (v12: data-model fix + Sandpiper, 2026-09-26), `1.2.1`, `1.2.2` (first unattended
GitHub Release, 2026-09-26). A release id in a column is therefore either a numbered id or one of these five strings.

## 2. Immutability

A release is never edited. Fixes go into the next release. Each release is a GitHub Release on
`OlmLab/infant-gut-catalog-data` (`data-v<semver>`, zip + sqlite + SHA256SUMS) and a Pages deploy (`site-v<semver>`);
Zenodo mints a DOI per data Release (owner step) — `releases.csv.doi` stays empty until it exists. Catalog entities
are keyed by archive accessions (BioProject, BioSample/run, PMID); cohort ids and finding ids are never renumbered.

## 3. Bitemporal columns

Every **fact table** gets three columns appended at the END (order fixed; existing columns, values and row order are
untouched — dropping the three columns reproduces the previous package's table exactly, asserted at build time):

| column | type | meaning |
|---|---|---|
| `release_added` | str | release in which this row (this value) first became visible |
| `release_retired` | str \| null | release that replaced/removed it; **null = current row** |
| `package_added` | str | semver of the package in which the row first appeared (`1.3.0` for rows new in R2026.1) |

Fact tables: `sample_determinations.parquet`, `universe_studies_all.parquet` (verdict rows), `study_metadata_wide.parquet`
/ `.csv`, `cohorts.csv`, `study_paper_links.csv`, `sandpiper_sample_summary.parquet`, `sandpiper_run_qc.parquet`,
`sandpiper_top_genera.parquet`, `sandpiper_study_panels.parquet`. **`sample_metadata_wide` is derived** (its values
come from `sample_determinations`) and carries NO release columns. In the shipped fact tables every row is current
(`release_retired` null); "current" in SQL = `release_retired IS NULL`.

### `sample_determinations_all.parquet` (new)

`sample_determinations` columns + `release_added`, `release_retired`, `package_added`, `retired_reason` (str|null),
`retired_change_stage` (str|null = the `value_history.change_stage`). It is the union of

* every current determination (`release_retired` null), and
* every **retired published value**, reconstructed from `value_history.parquet`: a row is a retired published value
  iff its `status` ∈ {`superseded`, `moved_to_parent_biosamples`, `recommitted_out_of_scope_host`,
  `recommitted_out_of_scope_isolate`} — it was the visible value in an earlier package and the package mapped from
  its `change_stage` replaced/removed it. `release_retired` = that package; `retired_reason` = `value_history.reason`;
  `release_added` = the package that added the retired value (`1.0.0` unless its own `src_track`/history says later).
  `sample_determinations_superseded.parquet` (223 rows) is the same set of rows as the `superseded` statuses of
  change_stages `sample_unit_fix` (75) and `auditor_review:B9` (148); it is cross-checked, not added twice.
* rows with `status` ∈ {`rejected`, `dropped`, `not_committed_duplicate`, `recommitted_out_of_scope_adult`,
  `auditor_finding_applied`} were **never published** (validator rejections, group-audit drops, duplicate candidates,
  the pre-history of a row that IS current, finding records) and are not rows of the bitemporal table; they stay in
  `value_history.parquet`.

Invariant: exactly one current row per (`sample_key`, `field_name`). Retired rows may repeat a key (a value can be
replaced more than once) — the site's per-field value timeline is `ORDER BY release_added`.

### Provenance of reconstructed `release_added` (pre-1.3.0 rows) — read before trusting a value

Packages before 1.3.0 carried no release columns, so `release_added` for rows that already existed in 1.2.2 is
**reconstructed** from `value_history.change_stage` (newest stage touching the (sample_key, field_name)) and from
`sample_determinations.src_track`, with the stage → package mapping verified against the package CHANGELOG.md:

| evidence on the row | release_added | exactness |
|---|---|---|
| `value_history.change_stage = owner_decision` (status superseded) touches the key | retired value: `release_retired='1.2.2'`; the current replacement is not a determination row (body_site_class lives in the wide table) | exact (CHANGELOG 1.2.2) |
| `auditor_review:R3-3` touches the key | retired value: `release_retired='1.2.1'` | exact (CHANGELOG v1.2.1 R3-3) |
| `auditor_review:B9` recommitted / `src_track = adult_scope_fix` | current row `release_added='1.2.0'` | exact (CHANGELOG "v1.2 — data-model fix … B9", 9,559 rows) |
| `auditor_review:B9` superseded (23 + 125) / `auditor_review:B2` moved (97) | retired value: `release_retired='1.2.0'` | exact |
| `sample_unit_fix` (75 superseded) / `src_track = sample_unit_fix` (3,632 run-level rows) | retired in / added in `'1.1.0'` | exact (CHANGELOG v1.1, release v11) |
| `auditor_review` (3 study-level finding records) | study_paper_links row PRJNA294605 ↔ 27258951: `'1.1.0'` | exact |
| no history (`r1_parse` and `group_statement_audit` rows were never published) | `'1.0.0'` | **assumed**: the row existed in the first package; the first package is not archived as a table, so this cannot be checked row by row |

`package_added` is set identically to `release_added` for all pre-1.3.0 rows (the historical ids ARE package
versions). Study verdict rows: `study_verdict_history.parquet` records no verdict change dated after the first
package (2026-09-25; the only 2026-09-26 rows are the consolidated-final copies), so `release_added='1.0.0'` for all
9,579 verdict rows is exact at the level of the verdict; the `outcome`/`reason_code` normalisations of v1.2.1 (R3-6)
are not treated as verdict changes. Sandpiper tables: `'1.2.0'` (CHANGELOG v1.2.0 "Sandpiper profiles"); the v1.2.1
recomputation (R3-1/R3-2, changed values on existing rows) is NOT modelled as retire+add because 1.2.0's rows are not
archived as a table — the CHANGELOG is the record. Cohorts and study_metadata_wide rows: `'1.0.0'` (assumed as above).

### 3.x Incremental releases (R2026.2 onward)
From package 1.3.0 every fact table already carries the release columns, so `bitemporal.py` runs in **incremental mode** when its
input has them (`strip_prior`): prior `release_added` / `package_added` are carried row by row; rows whose key is new since
`--previous-package`, or whose value columns changed, get the new release id (and the previous row enters
`sample_determinations_all.parquet` as retired with `retired_reason = row absent from / value changed in package <semver>`,
`retired_change_stage = apply_findings`); previously published retired rows are copied verbatim from the previous
`sample_determinations_all.parquet`; `releases.csv` carries the previous package's registry rows verbatim (dates, counts, DOI as
published) and appends the current row. A rebuild with no data change reproduces every 1.3.0 table exactly (asserted in
`tests/test_bitemporal.py`). The R2026.2 worklist tables (`contribute_worklist*.csv`, `config/releases.yaml: worklist_tables`) are
written by `make worklist` with their release columns already set and are not touched by `bitemporal.py`.

## 4. Registry — `releases.csv`

One row per release id, oldest first: `release_id, package_version, release_date, data_tag, site_tag, doi,
n_studies_included, n_samples, n_catalog_scope, n_determinations_current, sandpiper_version, notes_file`. Historical rows
are filled only where the CHANGELOGs state the number (else empty — never invented); the current row is computed from
the built tables. `doi` is filled by the owner after Zenodo mints it (next release carries the value).

## 5. How to cut a release (R2026.n)

1. Append the release to `config/releases.yaml: releases` (release_id, package_version, previous_*), bump
   `config/version.txt`, write the CHANGELOG entries (package + docs).
2. `make release BUILD_DATE=YYYY-MM-DD PKG_ZIP=data/inputs/data_package_v<prev>.zip` — unpack → findings → package-dir
   assembly → **bitemporal** (columns + `sample_determinations_all` + `releases.csv`) → package docs → `make_version`
   (VERSION.json with `release_id`/`previous_release_id`, deterministic zip) → **release notes**
   (`RELEASE_NOTES_<id>.md`, generated from prev vs new package; deterministic).
3. `make site verify`, then `make publish-branch` and push (RUNBOOK §6–7). Add the row to `docs/CYCLE_LOG.md`.

Rows new in the release get `release_added = <release_id>`, `package_added = <semver>`; rows of the previous package
that are gone get a retired row in `sample_determinations_all` with `release_retired = <release_id>` and
`retired_change_stage = apply_findings` (or the value_history stage when one is recorded for that key and package).

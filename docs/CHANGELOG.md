# CHANGELOG — Infant Gut Shotgun-Metagenome Catalog

Reconstructed 2026-09-26 from the artifact store (11 versions of `release_bundle.tar.gz` / `CATALOG_REPORT.md`,
timestamps UTC), `BUDGET.md` (per-phase token log) and `CATALOG_REPORT.md` / `EXTRACTION_REPORT.md` sections.
The mapping of report sections to bundle versions v2–v7 is **inferred from matching timestamps** (the bundle
itself carries no version string); numbers are copied from the reports. Going forward the public version is the
data-package **semver** (`config/version.txt`, `VERSION.json`), and release bundles/tags derive from it (A7).

| bundle | date (UTC) | package | site | what changed | LLM tokens (phase) |
|---|---|---|---|---|---|
| v1 | 2026-09-18 20:49 | — | — | First release. Universe 5,942 ENA studies (+144 gap-fill), cascade deterministic auto-exclude → Haiku screen (3,978 studies) → Sonnet rubric ×3 → Opus adjudication (290) + blind κ 200 (0.77/0.85); literature channel 12,859 papers (Haiku 25/request), accession mining, contested-link adjudication, supplementary-table rescue (8 includes), cohorts (188 clusters), recoverability tiers, extraction worklist. Gold recall 17/22 cMD. | 19.56 M |
| v2 | 2026-09-23 17:36 | — | — | Universe growth: fixed re-enumeration (v2 taxids), virome slice, literature snowball (S2 refs+cites), external repos (GMrepo, MGnify), misfiled `library_source=GENOMIC` (287 studies → 13 infant cohorts); 2,732 studies triaged, **+22 included**; GSA/GSA-Human non-INSDC annex listed. | 6.42 M |
| v3 | 2026-09-24 16:45 | — | — | Follow-up tracks: downstream assessment extended to all growth includes (`assessed_downstream`), worklist v2 (517 studies), GSA annex verdicts, **enumeration v3** (`scope_constants_v3`, four taxid corrections, runtime taxid guard) with 206-study delta (+1 include PRJEB35919). | 0.99 M |
| v4 | 2026-09-24 19:02 | — | — | Growth round 2: **frame-free sweep** of all 1.46 M METAGENOMIC WGS/WXS runs → 442 human-signal studies outside every taxon frame (237 blank tax_id), **+14 included cohorts (~10,300 samples)**; v3 full run refreshes 226 run counts; KoNA→K-BDS and CNGBdb probed (no joinable infant deposits). | 0.74 M |
| v5 | 2026-09-24 20:07 | — | — | Human-review round 2 merged (41 of 60 archive-only uncertains resolved: 7 include / 34 exclude / 19 unresolvable); downstream addendum #2; worklist v3 (429 open studies). | (in v4/v6 lines) |
| v6 | 2026-09-24 20:54 | — | — | Loose ends: 523 frame-free human/animal ties filtered to 38 and rubric-judged (0 include); sibling deposits of the paediatric-leukaemia cohort re-checked (PRJEB59728 include 0.58). | 0.16 M |
| v7 | 2026-09-24 22:45 | — | — | Growth round 3: BioSample-attribute sweep (312,686 flagged samples, 108 studies), cohort-name crosswalk (75 studies), reanalysis-link following, study_relations (2,379 rows), **+4 includes** (PRJNA1368374, PRJNA687137, PRJNA61745, PRJEB49206 overturned); `resweep_universe.py` monthly tool tested; submitter-outreach pack. | 0.29 M |
| v8 | 2026-09-25 11:27 | — | — | **Per-sample extraction** phases 0–3: sample frame (Haiku normalisation), pilot, R1 archive attributes / title parser, R2 supplementary tables (Haiku column classification + deterministic normalisation), R3 paper prose (Sonnet ×2, group scope), R4 abstract (Haiku + Sonnet gate); Opus conflict adjudication per pattern (76) and group-statement audit (359); gold eval vs cMD (age P .99). | 14.04 M |
| v9 | 2026-09-25 16:25 | — | — | Metadata-recovery round 2: R2 rescue, PDF/DOCX supplements + key fix, unitless-age rules U1–U3 (Sonnet ×2), multi-paper cohorts (Sonnet ×2 + Opus audit); exposure truth set attempted (safety-filter refusal, 0 tokens). | 2.70 M |
| v10 | 2026-09-25 21:24 | v1 (README "v1") | site v1 (774 pages) | Final passes: multi-paper pass 2, R2 full re-run with fixed ID gate, **field extension** (health_condition, multiple_birth, sibling_in_study, geo_subregion; `curation_kernel_ext`); 609 k determinations / 16 fields; **data_package_v1.zip** (README, DATA_DICTIONARY, wide tables, runs, determinations, notebook); static GitHub Pages site with DuckDB-WASM explorer; `infant_catalog.sqlite`. | 2.36 M |
| v11 | 2026-09-25 22:49 | v1.1 (README) / "v1" (footer, manifest, zip name) | rebuilt | **Sample-unit fix** from auditor findings (PRJNA294605 et al.): `sample_unit` ∈ {biosample, run, biosample_pooled}, `parent_biosample`, 6 one-BioSample-per-infant deposits keyed per run (521 rows), 75 rows moved to `sample_determinations_superseded`, `n_biosamples` on studies; `auditor_findings_applied.csv` (3 findings). Version-label drift noted by reviewers (A7/B11). | 0 (deterministic) |

Cumulative LLM spend to v11: ≈ 47.3 M tokens (CATALOG_REPORT §1; BUDGET.md).

## R2026.2 (in progress) — stage 3b gapfill
* `src/catalog/extraction/gapfill_samples.py` + `src/catalog/release/apply_gapfill.py` (+ `make gapfill` / `make apply-gapfill`, `tests/test_gapfill.py`, RUNBOOK §3b): package-shaped rows for new runs of an already-included study — cache-through harvest, deterministic R1 (field map vendored as `config/attribute_field_map.csv`), U3 paper-table unit rule with per-sample corroboration, composite subject ids, deterministic R2 gate, per-run Sandpiper API delta, no-existing-row-change assertion on apply. First run: PRJNA1140720 +150 saliva samples (mothers/fathers/siblings; body_site_class excluded), report `docs/reports/GAPFILL_PRJNA1140720_R2026.2.md`.

## 1.3.0 — 2026-09-26 — release R2026.1 (first numbered release; bitemporal data; deterministic, 0 LLM tokens)
Data (package CHANGELOG 1.3.0; `data_package_v1.3.0.zip`): release columns `release_added` / `release_retired` / `package_added` on 9 fact
tables (10 files), `sample_determinations_all.parquet` (618,898 current + 1,316 retired), `releases.csv`, `RELEASE_NOTES_R2026.1.md`,
`build_counts.json` regenerated (was stale at 1.2.1 / 71,795), README heading fixed (1.2.2 shipped "v1.2.0"). No 1.2.2 value changed.
Repo: `config/releases.yaml` + `docs/RELEASES.md` (release model, frozen column spec, CHANGELOG-verified change_stage → package
mapping: sample_unit_fix/auditor_review → 1.1.0, B2/B9 → 1.2.0, R3-3 → 1.2.1, owner_decision → 1.2.2); `src/catalog/release/`
(`bitemporal.py`, `release_notes.py`, `package_docs.py`); `make release` = unpack → findings → package-assemble → bitemporal →
package-docs → release-notes → make_version → zip → check (`package` still works); `make_version` writes `release_id` /
`previous_release_id` and `--check` verifies them; `PKG_ZIP` default → `data_package_v1.2.2.zip`; `docs/package_changelog/<semver>.md`
holds the package CHANGELOG entry; tests `test_bitemporal.py` (6) + `test_release_notes.py` (3); `audit/schema.json` schema_version 1.3.0.

## 1.2.1 — 2026-09-26 (fix wave after three independent final reviews; deterministic, 0 LLM tokens)
Data (DATAFIX_REPORT.md; `data_package_v1.2.1.zip`, artifact eb4d3d1a): see that report for the per-finding table.
Repo (REPOFIX_REPORT.md): model resolution works with the kernel `host` global (`set_host`, frame fallback, `python -m catalog.models` exits 1 on
UNRESOLVED); `bootstrap.py` exits 4 on missing required inputs and materialises only data groups; `requirements.lock` regenerated without
`file://` URLs + `environment.lock.yml`; `pyproject.toml` (package-dir `src`); `verify.yml` step-level test gate, `notify` job, `ref` passthrough;
`config/inputs.json` gains `data_package_v1.2.1.zip`, Sandpiper + authors inputs and the `reports` group; `src/catalog/sandpiper/` and
`src/catalog/authors/` modules with `make sandpiper-refresh / sandpiper-delta / authors`; deterministic package zip (fixed timestamps, zip sha256 in
VERSION.json, `--check` fails on unlisted tables); `apply_findings` rebuilds the wide table and study lists, emits only when ≥ 1 row applied,
`confirm` action → `confirmations.parquet` + `<field>__verified`; `audit/schema.json` single source for the Issue template / FINDING_COLS /
ACTIONS; `ingest_issues.py`; RUNBOOK 'Owner bootstrap (once)', Sandpiper/authors stages, budgets recomputed from `config/budgets.yaml`.

## 1.2.0 — 2026-09-26 (first semver release; package README, VERSION.json and zip name agree)
* Repo skeleton (this repository): package layout, `config/models.yaml` (no literal model ids), `inputs.json` with
  artifact ids + sha256, `apply_findings.py`, `make_version.py` → `VERSION.json`, workflows (verify / deploy-pages /
  release), issue template, RUNBOOK / SECURITY / ARCHITECTURE / DATA_LAYOUT. Validators synced to the skill kernel
  (artifact copy lacked the `external_curation.` source prefix).
* Integrate track: deterministic site build (gzip mtime 0, build date from VERSION.json), version regex fix,
  `biosample_pooled` excluded from counts (B2), `age_scope` (B1), history tables (B3), flag links (B4), Sandpiper columns.

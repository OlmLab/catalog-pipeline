# 1.8.0 — 2026-09-28 (release R2026.7, curated scope gut_all — "Microbiome Repo")
* **New curated scope `gut_all`** (config/packs/gut.yaml): every human gut shotgun-metagenome study in the registry, all ages — 2,837 studies / 579,252 samples — curated at sample level for age at collection, sex, BMI, country, health condition (config/vocab/health_conditions.yaml), antibiotic exposure, subject and timepoint. Tables: `gut_sample_determinations.parquet` (one row per sample × field with route, confidence, verbatim evidence quote and source), `gut_sample_metadata_wide.parquet` (one row per sample, fields with route/confidence, `age_category` + basis, `body_site_class`, `infant_scope`), `gut_studies.parquet` (registry columns + per-field coverage, age-category / health-condition distributions, curated depth).
* Routes for the 2,448 non-infant studies: **R1** archive attributes (registry normalisation + a gut attribute field map of 287 keys with deterministic parsers; key triage by the utility model), **R2** supplementary tables of open-access papers (exact-accession join gate, header-named columns, no model), **R4** cohort-wide statements from titles / ENA descriptions / abstracts (utility model, verbatim-quote check, confidence ≤ 0.5). Health-condition text → vocabulary codes by 20 rules + a utility-model pass over 3,719 distinct (key, value) pairs. R3 (full-text prose) not run for non-infant studies.
* **The infant catalog is the `infant_scope` filter of this scope**: its 389 studies' rows are copied verbatim (src_track `infant_catalog`) and win over archive-only values; `infant_scope = true` reproduces the infant catalog_scope (72,358 samples) exactly. The infant tables are unchanged.
* Site: renamed **Microbiome Repo**; new `gut/` section (coverage by age category, health conditions, countries, largest studies, DuckDB-WASM sample explorer with an "infant catalog scope" switch); home page leads with the registry → gut scope → infant scope; Methods › Curated scope gut_all; future plans (other body sites) stated on the home page.

# 1.7.1 — 2026-09-28 (release R2026.6, rebrand — no data change)
* The site and the package are now presented as the **Human Shotgun-Metagenome Catalog**: the registry tier (all human shotgun metagenomes, all body sites and ages) is the front door; the **Infant Gut Shotgun-Metagenome Catalog** is its first curated scope and keeps its name on its own pages (Studies, Cohorts, Sample explorer, Fields, Authors, Universe). Names live in `config/site.yaml` (`site.title`, `site.short_title`, `site.curated_scope_title`); repository names and the site URL are unchanged pending the owner's final choice of name.
* Package README heading and intro updated accordingly; every table is byte-identical to 1.7.0.

# 1.7.0 — 2026-09-27 (release R2026.5, scale-up S2: registry sample tier)
* **New table `registry_biosamples.parquet`** — one row per harvested BioSample of the 4,217 `human_all` registry studies outside the curated infant catalog (611,601 of 612,857 BioSamples resolved via ENA sample XML, NCBI BioSample for the misses). Attributes were harvested in full (13.5 M key/value rows, the working_data artifact `registry_biosample_attributes.parquet`) and the R1 fields normalised to the vocabularies: body site (config/vocab/body_sites.yaml), life stage + `age_days`, sex, ISO-3166 country, collection year; `disease_raw` is carried as free text. Normalisation = one utility-model pass over the 42,989 distinct (field, key, value) pairs (9.1 M tokens; docs/REGISTRY_S2_PILOT.md, config/budgets.yaml `registry_s2`); every value keeps its raw key/value provenance.
* `registry_studies.parquet` gains the sample roll-up columns (`n_biosamples_harvested`, `n_biosamples_with_site/age/sex`, `sample_body_sites`, `sample_life_stages`, `sample_countries`, `sample_age_days_median`) and `n_runs_sandpiper` (runs with a Sandpiper 2.0.0 community profile; 838,702 of 1.98 M registry runs). Where the study-level body site / life stage was unknown and ≥ 60 % of harvested samples agree, the primary is refined from the samples (evidence row `sample.attr.<key>`); codes present in ≥ 10 % of samples join the study's lists. Curated-verdict precedence: included infant studies are always `human_all`, assay `shotgun_dna`.
* **New tables `registry_study_papers.parquet`** (6,398 study × paper links from Europe PMC accession mentions + NCBI BioProject declared publications; 2,676 of 4,217 studies linked, 90 % open access), **`registry_authors.parquet`** (52,110 author rows, 18,527 with ORCID) and **`registry_bioproject_records.parquet`** (4,217 BioProject records) — docs/REGISTRY_S2_PAPERS.md.
* Curated infant scope unchanged (389 studies, 154,356 samples, 619,647 determinations).

# 1.6.0 — 2026-09-27 (release R2026.4, scale-up S1: registry tier)
* **New tier: the registry of ALL human shotgun metagenomes** (SCALE_UP_PLAN §2; docs/EXPANSION.md). The universe was enumerated over all of ENA without a taxon frame (slices S1 METAGENOMIC WGS/WXS, S2 misfiled GENOMIC on verified human-metagenome taxa, S3 OTHER/Targeted-Capture/WGA adjudication; every slice count-complete against ENA): **54,361 studies / 1,980,623 runs**. `registry_studies.parquet` classifies every study by host (human yes/no/mixed/unknown), assay, body sites and life stages (controlled vocabularies with UBERON anchors: config/vocab/*), population flags and scope memberships (config/scope.yaml), with evidence rows (≤12-word quotes) and a classification stage: deterministic prior (infant-universe verdicts), deterministic rule, Sonnet ×2 replicates, Opus adjudication, or pending. `registry_universe_audit.csv` records the per-slice ENA counts. `registry_runs.parquet` (all 1.98 M runs, 46 ENA fields) is attached to the GitHub Release as a separate asset (too large for the package zip and the Pages site).
* The infant catalog is unchanged and becomes the first *curated scope* (`infant_gut`) inside the registry; its 9,581 screened studies carry their infant verdicts as `in_infant_catalog` / `infant_reason_code`.
* Site: `registry/` landing with facets and a DuckDB-WASM registry explorer, one page per scope (`registry/scopes/<id>.html`), Methods › Registry classification.
* Counts for the curated infant scope are unchanged from 1.5.0 (389 studies, 154,356 samples, catalog_scope 72,358, 619,647 determinations).

# 1.5.0 — 2026-09-27 (release R2026.3, monthly cycle 2026-09b)
* **Re-sweep** of ENA for deposits first public since 2026-08-20 (`make resweep`): 225 studies not in the catalog, 2 with a human signal, both judged `exclude` / `site_excluded` in R2026.2 (PRJEB108618 adult skin; PRJEB124241 maternal reproductive-tract and tracheal samples). Universe 9,581 studies.
* **Gap-fill of an included study** (`make gapfill` / `make apply-gapfill`, new in this cycle): PRJNA1140720 (Modelling human microbiome transmission in a nursery setting) gained 150 BioSamples / 150 WGS runs published 2026-09-02. They are saliva samples of mothers (81), fathers (62) and siblings (7) — `body_site_class = excluded`, `catalog_scope = False`, roles mother/other — so the catalog-scope headline is unchanged while the study's sample count now matches ENA (1,013 → 1,163). 749 validated R1 determinations (country, sex, subject_id, timepoint_label; 149 ages, 145 of them adult and committed under the out-of-scope-adult convention; 1 age rejected as disagreeing with the paper table); subjects joined to the study's existing family keys (149/150). Sandpiper has not profiled any of these runs (per-run API confirmed; miss reason `published_after_snapshot_horizon`).
* Counts: 154,356 sample units (+150), 619,647 current determinations (+749), catalog_scope 72,358 (unchanged), 389 included studies.

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

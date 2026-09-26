# Site generator v2 (2026-09-26)

```
# 1. package 1.2.0 (v1.2 tables + Sandpiper + authors + VERSION.json); config/version.txt holds the semver
PYTHONPATH=src python -m catalog.build_package_v120 --v12 <unzipped v1.2> --sandpiper <dir> --authors <dir> \
    --extra-docs <dir with DATA_MODEL_FIX_REPORT.md> --out build/package --build-date 2026-09-26 --zip build/data_package_v1.2.0.zip
PYTHONPATH=src python -m catalog.make_version --package build/package --check
# 2. site (base_url from config/site.yaml; refuses the placeholder URL)
cd site_generator/gen && python build_site.py --package ../../build/package --out ../../build/site --reports <reports dir> --package-zip ../../build/data_package_v1.2.0.zip
python check_links.py ../../build/site          # broken must be 0
CATALOG_PACKAGE_DIR=build/package python -m pytest tests/test_build_determinism.py   # two builds byte-identical
```

* Deterministic (A2): build date = `VERSION.json.build_date`; every `*.csv.gz` has gzip mtime 0; sorted iteration; `sort_keys` JSON.
* Versioning (A7/B11): footer `package X.Y.Z · built DATE · generator SHA8 · release data-vX.Y.Z`; `data/VERSION.json`, `data/manifest.json` (sha256 per site data file); `<meta name="catalog-release">`.
* Counts (B1/B2): parent BioSamples live in `parent_biosamples.parquet` and are rendered as a block on their study page only; headline infant-scope numbers use `age_scope`.
* History (B3): study pages `Decision history` (study_verdict_history); explorer detail `Value history` (value_history.parquet on demand).
* Flag / confirm (B4): `issue_url()` (Python, study & cohort pages) and `catalogIssueUrl()` (static/site.js, explorer + authors) build `…/issues/new?template=catalog-finding.yml&labels=finding&<field id>=…` ≤ 6 kB; field ids mirror `.github/ISSUE_TEMPLATE/catalog-finding.yml`.
* Explorer (B13/B15): README-rule toggle (default on; `rule=0` in the URL turns it off) implemented as a DuckDB view `samples_rule` that masks R3/R4 values with confidence < 0.5 — used for results **and** exports; exact match on sample_key / biosample_accession / run_accession / secondary_sample before `LIKE`; `ENA run` labels; Sandpiper filters and top-genera bars.
* Front-end (A13/A15): jQuery 3.7.1 + DataTables 2.1.8 vendored in `static/vendor/` with SRI (`SRI.json`); DuckDB-WASM 1.29.0 stays on jsDelivr with an explicit failure message linking the CSV downloads.
* Colours: `static/site.css` `:root` holds the University of Colorado Boulder palette as CSS variables (`--cu-gold`, `--cu-black`, `--cu-dark-gray`, `--cu-light-gray`); colours only, no logo/wordmark.
* Per-study slices are `<PRJ>.csv.gz` + `.parquet` (gzip keeps the 143-column table under the 350 MB site budget).

## v3 (2026-09-26, final-review fix wave — see SITEFIX_REPORT.md)
* F7: only `CATALOG_REPORT.md` / `EXTRACTION_REPORT.md` are published from `--reports` (`PUBLIC_REPORT_DOCS`); `NEXT_STAGE.md`, `SCALE_UP_PLAN.md`, `RUNBOOK.md`, `STATE_BRIEF.md` never are; `(frame …)` session tokens are stripped from notes at build time and a post-build scan of every HTML page enforces both.
* F4/F6/F9: home cards state `BioSample units + run units` (asserted to sum to the sample count) and the `catalog_scope` denominator; study pages show `n_sample_rows` with the shared-BioSample note; ONE "studies profiled" definition (≥ 1 profiled sample row) with own-run and panel counts alongside.
* F3/F13/F9: panel caption from `sandpiper_study_panels` v2 columns (catalog scope, adequate depth, age-scope breakdown); no-panel message from `sandpiper_study_panel_status.csv` distinguishes "no catalog-scope samples" from "no profiles"; panel n is re-derived from the shipped wide table and asserted for every study.
* F1/R3-5: organisation strings rendered only from `organisations.parquet` rows with `display_eligible` (assert: no `SUB\d{6,}` or `@` anywhere).
* R3-6: decision history ordered by `stage_rank`, consolidated rows folded into one **final** line, `verdict_norm_note` shown.
* F5/F8/F11/F12/F17/F18/F20/F21/F22: explorer dynamic import + 20 s watchdog; run-accession fallback in the detail panel and `?q=` from the home search; WCAG-AA tag/masked/palette colours (see SITEFIX_REPORT contrast table); keyboard access (tabindex, Enter/Space, aria-sort, label for/id, Escape, focus); ligature-aware author search; issue-URL byte budget + 2-decimal confidences; escaped/text-rendered submitter strings; canonical links; sitemap includes docs; cohort unique-infant display from `cohorts.csv`.
* `tests/test_site_fixes.py` covers the regexes, palette sync/contrast and the URL budget.

## R2026.1 (2026-09-26, release history views — docs/ARCHITECTURE.md §5)
* `--releases-config config/releases.yaml` (default) — the frozen bitemporal spec shared with `src/catalog/release`; the package must carry `release_added`/`release_retired`/`package_added` on `sample_determinations` and `universe_studies_all`, plus `sample_determinations_all.parquet`, `releases.csv`, `RELEASE_NOTES_<release_id>.md`, and `VERSION.json.release_id` (build fails otherwise: the generator is >= 1.3.0 only).
* New pages: `releases/index.html` (registry + rendered notes + Cite box), `changes/index.html` + `changes/<release_id>.html` (aggregated per field / per study, < 2 MB each), study `#timeline`, explorer "Value timeline across releases" (`data/sample_determinations_all.parquet` loaded on demand; `EXPLORER_CFG.sdall`, `releaseCols`, `releaseId`).
* Cite box: Zenodo badge/latest-DOI URLs from `config/site.yaml github.data_repo_id` (GitHub repository id of `OlmLab/infant-gut-catalog-data`); "DOI: pending Zenodo integration" while `releases.csv.doi` is empty. Footer: `release <id> · package <semver> · build <sha> · built <date> · data tag <tag>`.
* Mock package for development/tests: `python tests/make_mock_release_package.py --src <unpacked 1.2.2> --out build/mock_package_1.3.0`; then `CATALOG_SITE_DIR=<site> CATALOG_PACKAGE_DIR=<pkg> python -m pytest tests/test_release_pages.py`.
* `check_links.py` also verifies `EXPLORER_CFG.sdall`. Deterministic build unchanged (two builds byte-identical with the mock package).

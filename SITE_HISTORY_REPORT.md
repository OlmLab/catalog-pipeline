# SITE_HISTORY_REPORT — R2026.1 Site track (branch `cycle/R2026.1-site`)
*2026-09-26. Generator work only: no harvest, triage, extraction or LLM curation; no curated value was committed. Built and tested against a MOCK 1.3.0 package (placeholder release columns) derived from data package 1.2.2.*

## 1. What was built
| file | purpose |
|---|---|
| `config/releases.yaml` | **frozen bitemporal/release spec** (ids, three column names, fact-table list, `_all` file, registry columns, page paths). Created on this branch because the clone had none; if the Data track also creates it, **keep the Data track's version** and re-run the generator tests — the generator reads only `release_id.historical/first_numbered`, `columns.*`, `files.*`, `registry_columns`, `site_pages.*`. |
| `config/site.yaml` | `github.data_repo_id: 1389758854` (GET https://api.github.com/repos/OlmLab/infant-gut-catalog-data → `id`, fetched 2026-09-26; comment in file). |
| `site_generator/gen/tests/make_mock_release_package.py` | builds the mock 1.3.0 package (rules in its docstring and §5 below). Placed under `gen/tests/` (the existing tests location), not `site_generator/tests/`. |
| `site_generator/gen/build_site.py` | loads the spec (`--releases-config`), asserts package/registry consistency, copies `sample_determinations_all.parquet` to `data/`, renders the new pages, study verdict timelines, explorer config, footer, manifest `release_id`. |
| templates `_cite.html`, `releases.html`, `changes_index.html`, `changes_release.html`; edits to `base.html`, `index.html`, `study.html`, `explorer.html` | see §2 |
| `static/explorer.js`, `static/site.css`, `check_links.py` | value timeline (on-demand `sdall` table), `.cite`/retired-row styles, `sdall` path check |
| `site_generator/gen/tests/test_release_pages.py` | 10 new tests (§4) |
| `docs/ARCHITECTURE.md` §5, `site_generator/gen/README.md` R2026.1 section | documentation |

## 2. What each page shows
* **`releases/index.html`** — lead text; the **Cite box**; registry table from `releases.csv` newest-first (release id, date, package, data tag → `https://github.com/OlmLab/infant-gut-catalog-data/releases/tag/<data_tag>`, site tag → site repo release URL, DOI link or "pending", n_studies / n_samples / n_catalog_scope / n_determinations_current, Sandpiper version, link to `changes/<id>.html`; empty historical counts render as "—" with an explicit "not stated in the changelog, never back-filled" note); every `RELEASE_NOTES_<id>.md` named in `notes_file` rendered with the generator's `markdown` (current release open) and copied as `.md` next to the page.
* **Cite box** (`_cite.html`, on home and releases): `Infant Gut Shotgun-Metagenome Catalog, release R2026.1 (data package 1.3.0), OlmLab, 2026-09-26.`; Zenodo badge `https://zenodo.org/badge/1389758854.svg` linking `https://zenodo.org/badge/latestdoi/1389758854`; **"DOI: pending Zenodo integration"** while `releases.csv.doi` is empty (release DOI link when present); the three upstream citations (ENA/INSDC; Woodcroft et al. 2025 *Nat Biotechnol* + Zenodo 20419175; curatedMetagenomicData Pasolli et al. 2017).
* **Footer (every page, extended not duplicated)**: `release R2026.1 · package 1.3.0 · build <sha8> · built 2026-09-26 · data tag data-v1.3.0 · DOI pending Zenodo integration (VERSION.json, what changed, changelog)`; `<meta name="catalog-release-id">`; `window.CATALOG.releaseId`. Nav gains "Releases".
* **`changes/index.html`** — one row per release (newest first): verdict rows added, determinations added, determinations retired, studies with value changes; "nothing changed in this release" state.
* **`changes/<release_id>.html`** — cards; study verdict rows with `release_added == id` (study link when included; **previous verdict** = last live `verdict_norm` in `study_verdict_history` that differs from the current verdict, else "no earlier differing verdict"; capped at 500 rows shown); determinations added / retired per field (rows, samples, studies; field link only for catalog fields, finding fields such as `body_site_class` shown as plain text); top-20 studies by rows changed (added, retired, samples affected, samples in study, fields, stage · up to 3 retired reasons, explorer deep link `samples/index.html?study=<PRJ>`); retiring change stages. Each page asserted < 2 MB.
* **Study pages `#timeline`** — "Verdict timeline across releases": every row of the study in `universe_studies_all` (current + retired), oldest first: release added (link to changes page), release retired / **current**, verdict + status, confidence, stage, reason code, evidence quotes. Kept separate from "Decision history" (within-release stage judgements) — they do not duplicate: the timeline is one row per release state, the history is one row per triage stage.
* **Explorer sample detail** — new "Value timeline across releases" section above the legacy "Value history": loads `data/sample_determinations_all.parquet` only when a detail panel opens (`ensureSda`, same `ensureFile` path as `det`/`vh`/`tg`), per field current row first (bold) then retired rows greyed, columns value (raw in parentheses when different), route/scope/tier, release added, release retired, retired reason · change stage, evidence quote · source; rows the README rule would hide (R3/R4 < 0.5) are marked with the existing `masked` class and tag; the default filters/`samples_rule` view are untouched.

## 3. SQL used by the value timeline (explorer.js; `RC` = `config/releases.yaml columns`)
```sql
SELECT field_name, value_normalized, field_value, route, scope, confidence, evidence_source, evidence_quote,
       "release_added" AS release_added, "release_retired" AS release_retired,
       "retired_reason" AS retired_reason, "retired_change_stage" AS retired_change_stage
FROM sdall WHERE sample_key = '<key>'
ORDER BY field_name, ("release_retired" IS NULL) DESC, "release_added" DESC, "release_retired" DESC
```
Replayed with the python `duckdb` package against the mock `sample_determinations_all.parquet` in `test_value_timeline_sql_replays_in_duckdb` (rows returned for a sample with a retired value; current rows precede retired rows within each field). The browser path (DuckDB-WASM) was **not** executed here — static review + brace balance only.

## 4. Build, tests, sizes (mock package; all numbers read from the built site / mock tables)
* `build_site.py --package build/mock_package_1.3.0 --reports data/inputs/reports --package-zip … --base-url https://olmlab.github.io/infant-gut-catalog/ --build-date 2026-09-26`: **787 pages** (1.2.2 baseline of the same generator: 777), 2,081 files, ~60 s. `check_links.py`: 151,564 internal links, **0 broken, 0 bad fragments, 0 root-absolute**. Two builds `diff -rq` identical (exit 0). F13 panel assertions unchanged and passing.
* New page sizes: `releases/index.html` 10,508 B; `changes/index.html` 5,519 B; `changes/1.0.0.html` 216,964 B; `1.1.0` 76,997 B; `1.2.0` 3,660 B; `1.2.1` 18,583 B; `1.2.2` 6,442 B; `R2026.1` 3,672 B; `data/sample_determinations_all.parquet` 7,590,080 B (on demand).
* Tests: `CATALOG_SITE_DIR=build/site_a CATALOG_PACKAGE_DIR=build/mock_package_1.3.0 python -m pytest site_generator/gen/tests` → **15 passed** (5 existing + 10 new: spec shape, release ordering, data_repo_id/Zenodo URLs, no placeholder URL in templates, explorer wiring; built-site: new pages exist + footer release id + Cite badge on 4 pages, releases page lists every registry row with tag links and "pending" DOI + a changes page per release < 2 MB, changes cards equal table counts per release, DuckDB SQL replay, study timeline present). Repo `tests/` (minus determinism): 103 passed, 27 skipped.
* Per-release change counts in the mock (from `sample_determinations_all` / `universe_studies_all`):

| release | verdict rows added | det. added | det. retired | studies with value changes |
|---|---:|---:|---:|---:|
| 1.0.0 | 9,362 | 657,127 | 36,244 | 381 |
| 1.1.0 | 217 | 0 | 0 | 0 |
| 1.2.0 | 0 | 0 | 0 | 0 (nothing-changed state) |
| 1.2.1 | 0 | 8,358 | 9,642 | 24 |
| 1.2.2 | 0 | 0 | 701 | 3 |
| R2026.1 | 0 | 0 | 0 | 0 (nothing-changed state) |

`sample_determinations_all`: 665,485 rows = 618,898 current + 46,587 retired (= value_history rows; `sample_determinations_superseded` is a checked subset). Registry: 6 rows.

## 5. Mock seeding (placeholder — NOT curated values, NOT the Data track's rules)
`release_added = '1.0.0'` everywhere except: current determinations whose (sample_key, field_name) has a value_history row with `change_stage = owner_decision` → `'1.2.2'`, `auditor_review:*` → `'1.2.1'`; sandpiper_* tables → `'1.2.0'`; verdict rows of studies with a `human_review` stage → `'1.1.0'`. Retired rows: `release_retired` `'1.2.2'` (owner_decision) / `'1.2.1'` (auditor_review:*) / `'1.0.0'` otherwise, `retired_reason = value_history.reason`, `retired_change_stage = value_history.change_stage`. `releases.csv`: 6 rows (1.0.0, 1.1.0, 1.2.0, 1.2.1, 1.2.2, R2026.1) — dates from the package CHANGELOG; counts only where the CHANGELOG states them (1.2.0: 154,206 samples, 618,898 determinations; 1.2.1: catalog_scope 71,795) or read from the 1.2.2 tables (1.2.2 and R2026.1: 389 / 154,206 / 72,358 / 618,898). `VERSION.json`: `release_id R2026.1`, `previous_release_id 1.2.2`, `package_version 1.3.0`, every file re-hashed; `build_counts.json` regenerated from the tables; README heading bumped to v1.3.0 (A7 check).

## 6. Deviations / not done
* Mock script lives at `site_generator/gen/tests/make_mock_release_package.py` (task said `site_generator/tests/`; the generator's tests already live under `gen/tests/`).
* `releases.csv` in the mock has 6 rows (the task listed 4: 1.0.0, 1.2.1, 1.2.2, R2026.1); 1.1.0 and 1.2.0 were added from the CHANGELOG so the registry covers every historical id in the spec.
* The explorer's value timeline was verified by static review and a DuckDB (python) replay of its SQL, not in a browser (no browser/node available); the Playwright smoke in `verify.yml` should open a sample detail and assert `#timeline` renders.
* `changes/` pages consider verdict rows and determinations only (per spec); Sandpiper/cohort/paper-link row changes are not listed (their release columns exist; listing them is a follow-up).
* `--reports` for the mock build used `CATALOG_REPORT.md`, `EXTRACTION_REPORT.md`, `field_coverage.png` extracted from the 1.2.2 site.zip (the clone has no `data/inputs/reports/`; not committed).
* Not pushed (no credential by design); no files under `/Users/Kira/` touched.

## 7. Merge notes for the root
* `config/releases.yaml` — reconcile with the Data track's copy (keep theirs; keys the generator needs are listed in §1).
* `config/site.yaml` — `github.data_repo_id` added (3 lines).
* `site_generator/gen/build_site.py` — additive; the generator now **requires** a ≥ 1.3.0 package (release columns, `_all` file, `releases.csv`, `RELEASE_NOTES_<id>.md`, `VERSION.json.release_id`). `Makefile site`/`verify` need no change except `PKG_ZIP` → 1.3.0 and adding `site_generator/gen/tests/test_release_pages.py` to the test run with `CATALOG_SITE_DIR`/`CATALOG_PACKAGE_DIR`.
* `docs/ARCHITECTURE.md` §5 appended; `site_generator/gen/README.md` section appended — merge textually with any Data-track edits to the same files.

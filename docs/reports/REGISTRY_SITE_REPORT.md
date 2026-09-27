# REGISTRY_SITE_REPORT — scale-up track S1 "Registry site" (branch `scaleup/S1-site`)

*2026-09-27. Base: OlmLab/catalog-pipeline main 8b6c506. Every number below is read from the tables and files this track produced (mock package `build/mock_package_1.6.0`, built site `build/site_mock`); the mock's synthetic rows are labelled as such and none of its counts is a finding about the real registry universe.*

## 1. What was built

| Piece | Path (branch) | Status |
|---|---|---|
| Registry spec (machine-readable copy of the frozen spec) | `config/scope.yaml`, `config/vocab/{body_site,life_stage,assay,population_flags}.yaml` | written by S1 from the frozen spec; **S0 files win at merge** |
| Mock 1.6.0 / R2026.4 package builder | `site_generator/gen/tests/make_mock_registry_package.py` | done |
| Generator: registry section | `site_generator/gen/build_site.py` (`read_scope_spec`, `read_vocabs`, `split_list`, registry block, deferred methods render, home/nav flags) | done |
| Templates | `templates/registry.html`, `templates/registry_scope.html`; edits to `base.html` (nav), `index.html` (stat card + section card), `methods.html` (§ Registry classification) | done |
| Explorer | `static/registry_explorer.js` — DuckDB-WASM over `data/registry_studies.parquet` | done (browser run not possible in the sandbox; SQL replayed with python duckdb) |
| Tests | `site_generator/gen/tests/test_registry_pages.py` — 10 tests | 10/10 pass; all 32 site-generator tests pass |
| Docs | `site_generator/gen/README.md` (§ Scale-up S1), `docs/ARCHITECTURE.md` (§ 7) | done |

### Pages
* `registry/index.html` (33,615 B): what the registry tier is vs the curated infant catalog (SCALE_UP_PLAN §2 wording), 6 summary cards, scope table (11 scopes with studies / runs / BioSamples and an "explore" link), 7 facet tables (studies and runs per body_site_primary, life_stage_primary, assay, scope membership, classification stage, host, access), the registry explorer.
* `registry/scopes/<scope_id>.html` × 11 (≤ 19,306 B each): definition, membership rule, 4 cards, per-scope facets, top-25 studies by BioSamples (included infant studies link to `studies/<acc>.html`, all rows link to ENA), pre-filtered explorer link `../index.html?scope=<id>#explorer`.
* Home: registry stat card + section card; nav "Registry" on every page; Methods › "Registry classification" (cascade, confidence meaning, body-site table with UBERON ids and match terms, life-stage table with day bounds, assay rules, scopes); `search_index.json` gains `t: scope` entries.
* Only `data/registry_studies.parquet` (864,647 B for the mock) is added to the site; `registry_runs.parquet` is documented as a Release asset and asserted absent from the site. No per-study pages for registry-only studies.

### Explorer (registry_explorer.js)
Filters: body site / life stage / scope (delimited `LIKE` on the `;`-joined list columns), assay / access / host / classification stage / infant verdict (equality), minimum runs, title-word or accession search (exact accession when the query looks like `PRJ…`). Columns: study (link to study page when `in_infant_catalog = include`, ENA link otherwise), title, n_runs, n_samples, sites, stages, assay, stage badge, ENA link. Row detail: infant verdict + reason code, classification block, the three evidence tables (host / body site / life stage; `{source, quote}` rows), archive aggregates. CSV export of the filtered slice (`COPY … TO`). URL state (`?scope=…&body_site=…&study=…`). Same boot / 20-s watchdog / failure text pattern as `samples/index.html`.

## 2. Verification (all on the mock build)
* `check_links.py build/site_mock`: 803 pages, **0 broken**, 0 root-absolute, 0 bad fragments (with `--reports`; without it the 5 pre-existing report-doc links are the only misses, as on main).
* Determinism: two builds from the same mock package → 2,110 files, **0 differing** hashes.
* Build-time assertions added: registry column order == `config/scope.yaml`; every code in body_sites / life_stages / scope_memberships within the vocabularies; `in_infant_catalog = include` set == `study_metadata_wide` (389); `in_infant_catalog` == `universe_studies_all.triage_verdict` for every screened study; facet sums == row counts; registry pages < 2 MB; no placeholder URL; F7 leak regex runs over the new pages (title/description/health_context pass through `strip_frame_tokens`).
* A 1.5.0 package (release R2026.3 < R2026.4) still builds (790 pages) with no registry section and no registry links.
* `tests/test_registry_pages.py` (CATALOG_SITE_DIR / CATALOG_PACKAGE_DIR set): spec shape, vocabularies (UBERON id format, day bounds), pages exist, explorer references the parquet, no placeholder / no leak, summary cards == table, 7 facet tables == pandas groupby, scope table == membership counts, scope pages (counts, top-25 accessions present, study-page links for includes, `infant_gut` == included set), home/nav/methods/search index, explorer SQL shapes replayed with python duckdb (count, page, list filter, title search, detail with ≤ 12-word quotes, CSV export).

## 3. Mock package numbers (mock only — NOT registry findings)
registry_studies.parquet: 11,981 rows × 42 columns = 9,581 infant-universe studies (deterministic priors) + 2,400 synthetic `signal_human_new` rows (accessions `PRJMOCK000001…`, titles prefixed `[MOCK]`). Host human yes 7,915 / no 3,688 / unknown 261 / mixed 117. Stage: deterministic_prior 10,302 · sonnet_x2 1,106 · pending 459 · opus_adjudicated 114. in_infant_catalog: exclude 9,140 · include 389 · uncertain 52 · not_screened 2,400. Scope memberships: infant_gut 389 · gut_child 361 · gut_adult 1,482 · oral 683 · skin 244 · vaginal_urogenital 302 · respiratory 711 · milk 58 · blood_tissue 521 · other_site 286 · unknown_site 2,348. Longest evidence quote: 10 words (body site), 7 (life stage), 2 (host).

Deterministic priors for the real rows follow the curation rules: host from the reason code (`host_*` → no); assay from `assay_*` reason codes; body site from `body_site_call`, else whole-word vocabulary terms in the study title (evidence `study.title` + span), else `unknown_site` (`other_site` for `site_excluded`); life stage from the verdict / `age_*` code, else title terms, else `unknown_age`; ENA aggregates (strategies, platforms, host tax ids, scientific names, center, secondary accession) computed from `runs.parquet` for the 389 included studies and left NULL otherwise (omit rather than guess). Evidence sources used: `external_curation.infant_triage`, `study.title`, and for synthetic rows `sample.attr.host_tax_id`.

## 4. Not done / caveats
* The explorer was not exercised in a browser (no browser or CDN in the sandbox); its SQL shapes are replayed with python duckdb in the test and mirror the proven `explorer.js` boot pattern. Playwright in Actions should add `registry/index.html` to the smoke list.
* `registry_runs.parquet` is not produced here (S0 track; ~1.5 M rows) and is only documented as a Release asset.
* No `data/registry_universe_audit.csv` page; the file ships under `data/package/` and is linked from the explorer footer.
* `FILE_DESC` / downloads page: the two registry files get descriptions; `OFFSITE` was not extended with `registry_runs.parquet` (one line to add once S0 fixes its size).

## 5. Merge notes
* `config/scope.yaml` and `config/vocab/*.yaml`: S0's files win; the generator reads only `scopes[].{id,label,definition,rule,curated}`, `registry_columns`, `classification_stages`, `host_human_values` (quoted strings — bare yes/no are YAML booleans), `access_values`, `assay_values`, `in_infant_catalog_values`, `files.{studies,audit}`, `vocab_dir`, `release_id`; vocab files need `codes.<code>.label` (+ `uberon`, `days`, `terms` for the Methods tables).
* `releases.yaml` needs the R2026.4 / 1.6.0 release row and `RELEASE_NOTES_R2026.4.md` (mock writes them into the package; the real `make release` must).
* `registry_studies.parquet` must carry the bitemporal columns and exactly the `registry_columns` order; `in_infant_catalog` must equal `universe_studies_all.triage_verdict` (asserted).
* Branch touches only `config/`, `site_generator/gen/`, `docs/`; no `src/catalog/` changes, so it should merge cleanly with S0.

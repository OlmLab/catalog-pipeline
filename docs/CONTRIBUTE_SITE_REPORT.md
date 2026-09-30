# CONTRIBUTE_SITE_REPORT — R2026.2 Site track (branch `cycle/R2026.2-site`)

Base: `OlmLab/microbiome_repo-pipeline` main `885072f`. Four commits on `cycle/R2026.2-site` (bundle `cycle_R2026.2_site.bundle`,
`git bundle create … main..cycle/R2026.2-site`; apply with `git fetch <bundle> cycle/R2026.2-site`). Nothing was pushed; nothing under
`/Users/Kira/` was modified. Every number below is read from the tables of the MOCK 1.4.0 package or the built mock site
(`report_numbers.json`) — the mock's blocker assignment is a placeholder (see "Deviations"), so **all counts are provisional** until the
Data track's real `build_worklist` output replaces the mock.

## 1. What was built

| Piece | Where |
|---|---|
| Frozen schema | `config/contribute.yaml` — blocker codes + labels, contribution types + labels, six fields + weights, `missing_threshold` 0.5, `worklist_columns` (38) / `fields_columns` (11), Issue-form ids, `issue_url` template, ingest gates. **Merge: the Data track's copy wins**; the generator reads only labels / vocabularies / columns / template. |
| Mock package builder | `site_generator/gen/tests/make_mock_contribute_package.py` — 1.3.0 → 1.4.0 mock: `contribute_worklist.csv`, `contribute_worklist_fields.csv`, `releases.csv` + R2026.2 row, `RELEASE_NOTES_R2026.2.md`, `VERSION.json` (release_id R2026.2, previous R2026.1, package 1.4.0). |
| Issue form | `.github/ISSUE_TEMPLATE/catalog-contribution.yml` — name "Catalog contribution", label `contribution`, ids `study_accession` (input, required), `contribution_type` (dropdown, 5 options, required), `source` (dropdown, 4 options, required), `source_url`, `licence` (required checkbox: CC-BY-4.0 or derived values only), `note` (textarea; attach by drag-and-drop), `attachment` (markdown instructions incl. no e-mail/participant names), `release_tag` (prefilled). `make install-workflows` now copies it into the site clone. |
| Ingest | `src/catalog/contribute/ingest_contributions.py` (CLI `--repo --package --out [--since] [--comment] [--from-json]`), `make ingest-contributions [SINCE_ISO=… COMMENT=1]`. |
| Generator | `site_generator/gen/build_site.py` (+`templates/contribute.html`, `study.html`, `index.html`, `base.html`, `static/site.css`). |
| Tests | `tests/test_ingest_contributions.py` (5), `site_generator/gen/tests/test_contribute_pages.py` (7: 4 spec-level, 3 built-site). |
| Docs | `docs/ARCHITECTURE.md` §6, `docs/RUNBOOK.md` §4b, `docs/SECURITY.md` §7, `site_generator/gen/README.md`. |

## 2. What the contribute/ page shows (mock build)

`contribute/index.html` — 1,357,260 bytes (< 2 MB budget; 439 rows ≈ 3.3 kB each), plus `data/contribute_worklist.json` (528,152 bytes,
one compact object per study; no per-sample rows anywhere).

1. **Header + summary cards**: 439 open studies (387 included, 52 inclusion-uncertain); 165,367 archive samples affected (71,559
   catalog-scope); 2,170 study × field gaps; one card per blocker — partial_coverage 274 · no_linked_paper 112 ·
   archive_only_uncertain 52 · controlled_access 1 (mock assignment).
2. **How to contribute**: the 5 contribution types with labels (from the config), keying advice (run/BioSample accession joins directly;
   paper sample names need an ID key), licence (CC-BY-4.0 or derived-values-only) and privacy (research metadata only, GitHub login is
   the hashed provenance), "what happens next" (Issue → deterministic ingest with the four verdicts → Curator review (R2 contract) →
   next release with `release_added` + attribution), **claim a task** = comment on the study's Issue; link to the label:contribution
   Issue list.
3. **Filters** (sticky bar): blocker (select, counts), missing field (select, counts per field: age 299 · delivery 363 · feeding 378 ·
   preterm 329 · antibiotics 381 · probiotic 420), contribution asked (per_sample_table 275 · paper_pointer 112 · verdict_evidence 52),
   minimum samples (number), verdict (include/uncertain), text search (accession, title, cohort, blocker code). Rows carry
   `data-blocker/-fields/-type/-n/-verdict/-k`; the filter is ~25 lines of vanilla JS (AND of all active filters, live "N shown"
   counter, empty-state line); query keys `?blocker=&field=&type=&min=&verdict=&q=` preselect, so study pages / e-mails can deep-link.
   Without JS the full table is still readable.
4. **Ranked table**: rank · study (link to the study page for included studies; accession + "uncertain" tag for human-review studies,
   which have no catalog page) with title and controlled-access tag · cohort (linked only when a cohort page exists) · samples /
   catalog-scope · six **coverage chips** (`age 10% R2` … missing fields highlighted, covered ones muted; tooltip = full label,
   coverage, predicted tier) · blocker label + detail · "what would unlock this" · papers count + up to 3 PubMed links · ENA/NCBI ·
   **Contribute** button = `issue_url` from the table.
5. Top of the mock ranking: PRJNA510445 (1,279 catalog-scope samples, 6 fields missing, 30.18) · PRJNA1274040 (1,000; 30.00) ·
   PRJNA900180 (830; 29.20) · PRJNA1123170 (760; 28.81) · PRJEB49383 (2,351; 5 fields; 28.66).

**Study pages**: worklist studies get the `#help-complete` panel (rank of N, verdict, catalog-scope n, priority; chips; blocker label +
code + detail; unlock text; `Contribute: <type label>` button = `issue_url`; link to "How contributions work"; one-line licence/privacy
note). The two complete studies of the mock (PRJEB39610, PRJEB74322) have no panel (test-covered). **Home**: stat card "439 studies need
metadata — contribute" (165,367 samples) linking to `contribute/`, plus a Contribute section card. **Nav + footer** link.

**Build guards added** (all in `build_site.py`): worklist/fields columns == `config/contribute.yaml`; blocker/type/verdict vocabularies;
rank 1..n; `missing_fields` count == `n_missing_fields`; fields table covers exactly the worklist studies; every `issue_url` is a
GitHub URL with `template=catalog-contribution.yml`, no placeholder, and the first 5 equal the template rebuilt from the config;
included worklist studies have a study page; F13: worklist `n_catalog_scope` == `study_metadata_wide.n_catalog_scope`; field-gap total
agrees between the two tables; one Contribute button per row; page < 2 MB. A package of release ≥ R2026.2 without the worklist fails the
build; a 1.3.0 package builds as before (no page, no nav link — verified: 785 pages, `has_contribute: false`).

Build results (mock 1.4.0 + reports dir): 789 pages, 245 MB, `check_links` **0 broken / 0 root-absolute / 0 bad fragments**, two
consecutive builds byte-identical (`diff -rq` empty). CU Boulder palette kept (black/gold chips and panel; new CSS block at the end of
`site.css`).

## 3. Ingest verdict rules (`ingest_contributions.py`)

* Issues: `GET /repos/{repo}/issues?labels=contribution&state=open[&since=ISO]`, paginated; token from `GITHUB_TOKEN`/`GH_TOKEN` only as
  the `Authorization` header to `api.github.com`, never sent to attachment hosts, never printed; anonymous read without a token.
* Form body: `### <id>` blocks → values (`_No response_` → ''); `licence_ok` = a checked box; e-mail patterns are stripped from `note`
  and `source_url`; an assertion refuses to write a manifest containing an e-mail.
* Attachments: `github.com/user-attachments/files/…`, `…/assets/…`, `user-images.githubusercontent.com/…`. Gate BEFORE download:
  extension must be in `.csv .tsv .txt .xlsx .xls` (`.exe .sh .py .zip .gz .tar …` → `rejected`); gate after: ≤ 50 MB. Files are saved
  under `audit/contributions/<issue>/` with `manifest.json` (issue number, url, sha256, size, uploader login + sha256 prefix, created_at,
  declared study/type/source/licence_ok/note/release_tag, verdict per file).
* Tables: pandas, `dtype=str`; all sheets for xlsx/xls; delimiter by extension or tab/comma count.
* Joinability: a column is an identifier candidate when ≥ 2 non-empty values, ≥ 50 % unique, ≥ 80 % short space-free tokens. Every
  candidate is matched **exactly** against the declared study's keys from the package: `runs.run_accession`, `runs.library_name`,
  `runs.secondary_sample_accession`, `runs.sample_accession`, `sample_metadata_wide.sample_key / secondary_sample / sample_title /
  biosample_accession`. Threshold = max(20, ceil(0.5 × rows)).
  * `accepted_for_review` — one column reaches the threshold against one key type (any sheet);
  * `duplicate_of_existing` — sha256 already in an earlier `manifest.json` under the out dir (or earlier in the same run);
  * `unjoinable` — no column reaches it; REPORT lists the top-3 candidate columns with match counts and the observed ID form
    (`run_accession | biosample | secondary_sample | experiment | bioproject | subject_timepoint | numeric | alnum_code | free_text`;
    ties on 0 matches prefer named-ID forms over numeric/free text) and says which key is missing;
  * `rejected` — extension/size/unreadable/no rows/no attachment.
  Issue verdict = best verdict over its files; `report.json` + `REPORT.md` per issue; `INGEST_SUMMARY.json`; `--comment` posts REPORT.md.

## 4. Tests

* `PYTHONPATH=src CATALOG_PACKAGE_DIR=build/mock_package_1.4.0 pytest tests/test_ingest_contributions.py` → **5 passed**: form parsing +
  attachment discovery; type/size gates; synthetic joinability (30/30 SRR → accepted, 10 matches < max(20,15) → not joinable,
  `T1_S23`-style ids → unjoinable with form `subject_timepoint`); verdict priority + duplicate + multi-sheet xlsx; end-to-end
  `process_issue` against the mock package with a fake downloader (accepted 60/60 run accessions, unjoinable + rejected `.sh`, duplicate,
  no-attachment/unknown study), manifests carry no `@`.
* `CATALOG_SITE_DIR=build/site_mock CATALOG_PACKAGE_DIR=build/mock_package_1.4.0 pytest site_generator/gen/tests` → **22 passed**
  (7 new: config shape; Issue-form ids/options match the config; `issue_url` parses to the expected query; templates reference the page
  and no placeholder; one row + one button per worklist study and every URL parses; panel present on PRJNA510445 and absent on both
  complete studies; home card/nav/sitemap).
* Repo suite `pytest tests --ignore tests/test_bitemporal.py --deselect tests/test_build_determinism.py` → 106 passed, 31 skipped,
  1 failed (`test_release_notes::test_real_pair_1_2_2_to_1_3_0`) — that failure and the `test_bitemporal` fixture error are
  **pre-existing on main** (verified with `git stash`): they expect `data/inputs/data_package` to be the 1.2.2 package without release
  columns, while this checkout unpacks 1.3.0. Not touched (out of scope; recorded as not_fixed).

## 5. Deviations / not done

1. **Mock blockers are placeholders**: the brief's rich inputs (extraction_worklist v3, recoverability.parquet, RESCUE_REPORT_v2,
   r2_rescue_studies, supp_inventory, controlled_access_registry, outreach_contacts) were NOT used on this track — the brief assigns the
   real table-building to the Data track (`build_worklist`). The mock assigns `no_linked_paper` (0 study_paper_links rows),
   `controlled_access` (flag), `archive_only_uncertain` (uncertain verdict) or `partial_coverage`; tiers come from `recov_*`; coverage
   from `study_field_coverage_matrix` (371 studies) or `cov_*` (18 studies without a matrix row) or 0 (52 uncertain studies);
   `n_supp_tables_inventoried` = 0; uncertain studies get priority 0 (n_catalog_scope 0). Hence 439 open studies here vs 429 in the
   extraction worklist — provisional.
2. Visual check not performed: no Playwright in the env and headless Chrome aborts in the sandbox; HTML of the three sample pages parses
   balanced; the filter JS could not be syntax-checked (no node) — Playwright smoke runs in Actions `verify.yml`.
3. `test_build_determinism.py` (subprocess double build) was not run through pytest; the equivalent double build + `diff -rq` was run by
   hand and is identical.
4. Not in scope of this track and not done: real `build_worklist.py`, package 1.4.0 / Release data-v1.4.0, deploying site 1.4.0,
   RESTART_HERE.md refresh, `ingest_contributions` as an Actions cron.

## 6. Merge notes for the Data track

* `config/contribute.yaml`: created here from the brief's frozen schema — if the Data track's file exists, take theirs and re-run
  `pytest site_generator/gen/tests/test_contribute_pages.py` (spec-level tests pin the vocabularies and column order).
* The generator asserts `contribute_worklist.csv` columns **in the exact order** of `worklist_columns`, `rank` 1..n, no `complete`
  blocker, `issue_url` built by the config template (`title` URL-encoded, other params raw) — `build_worklist` must use the same rule
  (`contribute_issue_url()` in `build_site.py` / `build_issue_url()` in the mock script show it).
* `releases.csv` needs the R2026.2 row and `VERSION.json` release_id R2026.2 before the site builds (`make release` does this).
* `make install-workflows` now also copies `catalog-contribution.yml` — owner must commit + push `.github/` of the site clone once.

# REPOFIX_REPORT.md — pipeline_repo_v2 → pipeline_repo_v3 (final; 29 min wall in-sandbox)

Deterministic, no LLM tokens. `site_generator/` untouched (parallel track merges its folder into this v3).

## Findings status (summary)

- **R1-01**: fixed
- **R1-02**: fixed
- **R1-03**: fixed
- **R1-04**: fixed
- **R1-05**: fixed (docs + make install-workflows; the owner actions themselves remain owner-only)
- **R1-06**: fixed
- **R1-07**: fixed
- **R1-08**: partial: inputs.json reports group + make check-reports guard + scripts/plot_field_coverage.py; build_site.py hard-fail is site_generator/ (other track)
- **R1-09**: fixed
- **R1-10**: not_fixed: agent-profile change (host.agents) is owner/profile track, not repo — REPOFIX_REPORT lists the exact excludedTools/prompt edits
- **R1-11**: fixed
- **R1-12**: fixed (docs/NEXT_STAGE.md + docs/SCALE_UP_PLAN.md in repo and new artifact versions; scripts/budget_calc.py)
- **R1-13**: fixed
- **R1-14**: fixed
- **R1-15**: fixed (make check-credential + scripts/git_askpass.py; env-var name still unverified — no credential stored)
- **R1-16**: fixed
- **R1-17**: fixed
- **R1-18**: fixed
- **R1-19**: partial: Makefile parses site.yaml with PyYAML and compares to placeholder; site.js/build_site.py are site_generator/ (other track)
- **R1-20**: not_fixed: owner action (sync/push after fixes land); RUNBOOK §0a/§7 document the release-branch path
- **F2**: fixed (repo side: schema, confirm action, ingest_issues; site.js/Auditor profile text are other tracks)
- **R3-4**: fixed (prepare_inputs.py is a reconstruction — provisional)

## Scope and method
Track "Repo fix" of the post-review fix wave. Input `pipeline_repo_v2.zip` (version 634088af) → `pipeline_repo_v3.zip`.
Deterministic edits only (no LLM calls, no values from memory: every artifact id / sha256 written into `config/inputs.json` was
read from the artifact store at fix time). `site_generator/` was **not touched** (parallel track). Tests: see the pytest
summary at the end; the determinism test ran against the real v1.2.1 package unpacked under `data/inputs/data_package`.

## Per-finding table

| id | status | change | file:line | test evidence |
|---|---|---|---|---|
| R1-01 | fixed | `set_host()` + `_looks_like_host()` + caller-frame-globals fallback in `_host()`; `main()` exits 1 on any UNRESOLVED role; all 56 script headers now `set_host(globals().get("host"))` and `MODEL = globals().get("MODEL") or resolve_model(...)` (lazy default) | src/catalog/models.py:83, src/catalog/models.py:95, src/catalog/models.py:155, src/catalog/triage/run_sonnet_confirm.py:15, src/catalog/triage/run_sonnet_confirm.py:26 | `tests/test_models_host.py` (7 tests: header exec'd in a dict namespace holding a fake `host`, preset MODEL short-circuit, frame fallback without set_host, `python -m catalog.models` rc 1 / rc 0) |
| R1-02 | fixed | exit 4 when a `required` input is MISSING (list printed to stderr before tests; tests not run then); only non-`code` groups materialised (into `data/inputs/<group>/`); `skill:` sources skipped; `__file__`-less exec supported; kernel form documented + `make bootstrap-kernel`; `--allow-missing` for CI | bootstrap.py:84, bootstrap.py:162, Makefile:43, RUNBOOK §0 row 1 / §9 step 4 | manual: `python bootstrap.py --no-env --only-required --data-root /nonexistent` → rc 4, 3 required entries listed, "tests NOT run" |
| R1-03 | fixed | `config/inputs.json`: `data_package_v1.2.1.zip` (version eb4d3d1a, sha256 063cc1f3…) required, v1 demoted; new groups `sandpiper` (7 incl. per_acc_summary ff108edb, match table b35c12de, bulk snapshot 8071e8b8) and `authors` (6); six scripts vendored under `src/catalog/sandpiper/` + `src/catalog/authors/` with code entries (artifact sha256 + sha256_repo); `make unpack PKG_ZIP=…` explicit + flattens a single top dir; `build_package.py` (generalised; flat deterministic zip) + `make package-merge`; `build_package_v120.py` is a shim | Makefile:12, Makefile:64, Makefile:138, src/catalog/build_package.py:4 | `make unpack` on the real v1.2.1 zip → "flattened package_v1.2.1/", 51 files; `tests/test_inputs_hashes.py::test_current_package_is_required_and_v1_is_not`; `test_data_input_hash[data_package_v1.2.1.zip]` passes on the materialised zip |
| R1-04 | fixed | `requirements.lock` regenerated with `pip list --format=freeze` (0 `file://` lines; `appnope` gets a darwin marker); `environment.lock.yml`; `make lock`; verify.yml installs the lock in a clean venv | requirements.lock:1-3, environment.lock.yml:1, Makefile:47, .github/workflows/verify.yml:45 | `pip install --dry-run -r requirements.lock` resolves; `grep -c file:// requirements.lock` = 0 |
| R1-05 | fixed (docs + target) | RUNBOOK §0a "Owner bootstrap (once)" (create repos, first push, clone, install workflows/template, Pages = Actions, rulesets, PAT); SECURITY §2a; `make install-workflows`; `publish-branch` rsync no longer excludes `.github` wholesale (only the installed workflows/template); `config/site.yaml github.issues` = single place for the Issues repo/template/label | docs/RUNBOOK.md:44, Makefile:170, Makefile:179, config/site.yaml:18 | `make -n install-workflows` renders; owner actions themselves cannot be executed by the agent |
| R1-06 | fixed | `apply_findings.rewide()` rewrites `sample_metadata_wide` cells (+`__confidence`, `__route`), `universe_studies_all.catalog_status/decision_stage`; samples of a newly `excluded` study leave the wide table (→ `sample_metadata_wide_excluded_by_review.parquet`); tables emitted only when ≥1 applied (`APPLIED` marker); route `H` default for `external_curation.*`; `make package` always re-runs `findings` and copies only when APPLIED | src/catalog/apply_findings.py:263, src/catalog/apply_findings.py:211, src/catalog/apply_findings.py:357, Makefile:131 | `tests/test_apply_findings.py` (6): no-op emits nothing; supersede → wide cell/route H + long/wide consistency loop; exclusion → universe + wide; real package no-op run: `n_applied 0`, only DIFF + log written |
| R1-07 | fixed | job-level `hashFiles` removed → step-level `has_tests` gate after checkout; separate `notify` job `needs:[unit-tests, site-checks, explorer-smoke]` + `if: failure()` naming the failed job; `ref` workflow_call input passed to every checkout; deploy-pages passes `inputs.ref || github.ref` | .github/workflows/verify.yml:39, .github/workflows/verify.yml:148, .github/workflows/deploy-pages.yml:39 | both YAML files parse (PyYAML); jobs = unit-tests, site-checks, explorer-smoke, notify |
| R1-08 | partial | `config/inputs.json` group `reports` (CATALOG_REPORT, EXTRACTION_REPORT, NEXT_STAGE, SCALE_UP_PLAN, field_coverage.png [+ summary csv]) materialised into `data/inputs/reports/`; `make check-reports` fails the site build when a required report is missing; `scripts/plot_field_coverage.py` + `make plot-coverage`; RUNBOOK §6 text | Makefile:141, Makefile:151, scripts/plot_field_coverage.py:1 | `test_inputs_json_shape` asserts the group; making `build_site.py` itself hard-fail is in `site_generator/` (other track) |
| R1-09 | fixed | `audit/schema.json` single source (columns, finding_type→actions, action→needs, routes incl. H, fields, reason codes = kernel REASON_CODES); `catalog.findings_schema` renders the Issue form (no empty dropdown option; evidence optional for confirmed_correct; reason_code + route dropdowns; date/source not asked) and `--check`/`--auditor-vocab`; apply_findings reads FINDING_COLS/STRUCT_COLS/ACTIONS/finding types from it and rejects type/action mismatches | audit/schema.json:1, src/catalog/findings_schema.py:46, src/catalog/apply_findings.py:52 | `test_template_matches_schema`; `test_unknown_action_and_type_mismatch_rejected`; template parses with PyYAML, 14 form fields, no '' options |
| F2 | fixed (repo side) | `confirm` action → `confirmations.parquet` (appends to an existing one) + `<field>__verified` on the wide row (study-level confirmations recorded); `add_study` → `candidates_<date>.csv`; `src/catalog/ingest_issues.py` (GitHub Issues API, issue-form body parser, `date`=created_at, `source`=issue#N, dedup against earlier `*_issues.csv`, offline `--from-json`) + `make ingest-issues`; RUNBOOK §4 / audit/README document the loop | src/catalog/apply_findings.py:231, src/catalog/apply_findings.py:12, src/catalog/ingest_issues.py:1, Makefile:125 | `test_confirm_writes_confirmations_and_verified_flag`; `tests/test_ingest_issues.py` (form body → row → CSV → `read_findings`; second run skips seen issue). The site buttons (`site.js`) and the Auditor profile vocabulary are other tracks |
| R1-11 | fixed | `make_version.build_zip()` (python zipfile, sorted, ZipInfo.date_time = build_date, 0o644) + `.sha256` sidecar + sidecar `VERSION.json` with `package_zip`; `--zip` option; `check()` fails on unlisted TABLE_EXT files, on a missing VERSION.json and on zip/sidecar mismatch; VERSION.json written last by `make package` | src/catalog/make_version.py:100, src/catalog/make_version.py:164, Makefile:134 | `tests/test_make_version.py` (3); real v1.2.1 package zipped twice 1 s apart with a touched mtime → identical sha256 3585c92d… (62,353,162 bytes), `--check --zip` OK |
| R1-12 | fixed | `scripts/budget_calc.py` derives every figure from `config/budgets.yaml`; SCALE_UP_PLAN §4 S1 = 4.0–7.2 k tokens/study → 24–58 M, 12–29 leaf frames at the 2.0 M hard cap / 80–193 at the 300 k soft cap; S2 Haiku line marked unmeasured (S0 pilot required); S4 = 0.8 M typical / ≤1.5 M; §3 per-scope Pages repos + registry index site replaces "federated"; §7 derivation table; NEXT_STAGE §7 = one table cross-referenced to RUNBOOK §8 (146 → 108 judged → 0.43–1.03 M; 6 includes → 0.28–0.55 M); EXPANSION.md / scope.yaml marked "planned (S0)"; `sandpiper/` path corrected. Copies in the repo (`docs/`) and as new artifact versions (NEXT_STAGE.md 47ea5985, SCALE_UP_PLAN.md 240b2991); inputs.json `reports` entries point at them | docs/SCALE_UP_PLAN.md §3/§4/§7, docs/NEXT_STAGE.md §2/§3/§7, docs/RUNBOOK.md:247 | `python scripts/budget_calc.py` output reproduced in SCALE_UP_PLAN §7 |
| R1-13 | fixed | README/RUNBOOK/Makefile no longer say "determinism xfail"; CHANGELOG has a 1.2.1 entry and 1.2.0 heading (was "Unreleased"); Makefile triage/extract point to §2/§3; leaf budget = 0.3 M soft cap from budgets.yaml (2.0 M hard cap named); `pyproject.toml` (package-dir src, dynamic version from config/version.txt, prompts as package data) | pyproject.toml:1, README.md:18, docs/CHANGELOG.md:25, docs/RUNBOOK.md:147 | `pip install --dry-run --no-deps -e .` → "Would install catalog-pipeline-1.2.0" |
| R1-14 | fixed | Sandpiper delta = Curator stage 1b (`make sandpiper-delta`); snapshot artifact 8071e8b8 (sha256 from download_log.json a1e5a7a3) recorded in inputs.json group `sandpiper`; DATA_LAYOUT amended to "host copy + one snapshot artifact per Zenodo version"; RUNBOOK §9 step 1 | docs/RUNBOOK.md:98, docs/DATA_LAYOUT.md:29, Makefile:101 | `make -n sandpiper-delta` renders; the RELEASE_ENGINEER prompt (profile) is not repo content |
| R1-15 | fixed | `scripts/git_askpass.py` (GIT_ASKPASS helper: host.credentials → GITHUB_TOKEN/GH_TOKEN/CATALOG_GITHUB_TOKEN; `--check` runs `git ls-remote` per clone) + `make check-credential`; SECURITY §3 paragraph (env-var name marked unverified) | scripts/git_askpass.py:1, Makefile:167, docs/SECURITY.md:50 | `git_askpass.py "Username…"` → x-access-token; `--check /nonexistent` → FAIL, rc 1, "token source: NONE" |
| R1-16 | fixed | applied outputs go to `build/applied_<version>/`; `package` depends on a fresh `findings` run and copies only when `APPLIED` exists | Makefile:17, Makefile:131 | `make -n package` shows the sequence |
| R1-17 | fixed | `harvest_lib`: cache dir from `CATALOG_CACHE_DIR` (default `~/catalog/cache/harvest_cache`; a cwd `harvest_cache/` still wins), directories created lazily (`_ensure_dirs()` before sqlite/blob writes); `make resweep` uses `--out .` | src/catalog/harvest/harvest_lib.py:68, Makefile:92; authors script re-uses it via a path shim | `tests/test_harvest_lib_import.py` (import from an empty tmp cwd creates nothing) |
| R1-18 | fixed | skills entry `version_id: null` (test allows it for `skill:` sources; bootstrap skips them); `site.zip` entry marked as an OUTPUT retained for provenance, not required | config/inputs.json:1066, tests/test_inputs_hashes.py:35 | `test_inputs_json_shape` |
| R1-19 | partial | Makefile parses `site.yaml` with PyYAML; `site` refuses when `base_url == placeholder_base_url` (no literal 'olmlab' test); Issues repo/template/label in `site.yaml github.issues` | Makefile:23, Makefile:155 | `build_site.py` / `site.js` reading it is `site_generator/` (other track) |
| R3-4 | fixed (provisional part flagged) | `src/catalog/sandpiper/{download_bulk,filter_bulk,build_sandpiper_tables,sandpiper_lib,render_report,prepare_inputs}.py` + README, `src/catalog/authors/harvest_bioproject_authors.py`; Zenodo record/version/taxonomy via env (`ZENODO_RECORD=… SANDPIPER_VERSION=…`); `make sandpiper-refresh / sandpiper-delta / authors`; RUNBOOK stages 1b/1c/1d with runtimes and request counts | src/catalog/sandpiper/README.md:1, src/catalog/sandpiper/download_bulk.py:6, Makefile:94, Makefile:111 | `prepare_inputs.py` ran on the real inputs: matched_runs 87,125 · sample_run_totals 154,206 · sample_scope 154,206 · run_qc_input 87,125 (0 runs without QC) — a RECONSTRUCTION of four intermediates whose original producer was inline session code; its outputs are provisional until a rebuild reproduces the shipped tables. RE prompt mention = profile track |
| R1-10 | not_fixed | agent profiles live in `host.agents`, not the repo. Recommended edits (for the profile track): CATALOG_AUDITOR excludedTools = [request_host_access, edit_file, delete_host_files, manage_environments, manage_packages, request_network_access]; remove `customize` (and figure-style) from RELEASE_ENGINEER; create CURATOR (RUNBOOK stages 1–4 incl. 1b–1d, skills infant-curation-rules + infant-catalog-harvest); RE rule "never rm -rf; rsync --delete only into build/ and clone working trees; never git clean outside a clone"; both prompts: "repo at ~/catalog/catalog-pipeline; if absent unzip artifact pipeline_repo_v3.zip"; Auditor finding_type vocabulary = `python -m catalog.findings_schema --auditor-vocab` | — | — |
| R1-20 | not_fixed | owner action after the fix wave lands (sync to ~/Downloads/site or push `release/1.2.1` per RUNBOOK §7/§0a step 5) | — | — |

## Left for other tracks / owner
* **Data track defect found while testing**: `data_package_v1.2.1.zip` (eb4d3d1a) README heading still reads "data package v1.2.0" while VERSION.json says 1.2.1 → `make_version --check` fails on it ("README.md says v1.2.0 but config/version.txt says 1.2.1"). The package builder must regenerate the heading; this track did not edit the package.
* `site_generator/`: build_site.py hard-fail on missing reports (R1-08), reading `github.issues` from site.yaml (R1-19/F2), Confirm buttons emitting `action=confirm` with `finding_type=confirmed_correct` (already the case per F2) — site track.
* Agent profiles (R1-10, R1-14 RE prompt, R3-4 RE prompt, F2 Auditor vocabulary) — profile track; exact text above.
* Owner: RUNBOOK §0a steps 1–8 (repos, first push, workflows install, Pages source, rulesets, PAT), then R1-20.

## Deviations
* `prepare_inputs.py` is a reconstruction (see R3-4); every other vendored script is the artifact byte-for-byte plus the documented env/path shims (recorded in inputs.json `changes`).
* `environment.lock.yml` was generated from the pip freeze (conda is not available in the sandbox), not from `conda-lock`.
* Group 4 "remaining low R1-* items": R1-10 and R1-20 are owner/profile actions and were not executed here.
* The sha256 of the 3.7 GB bulk snapshot was copied from `download_log.json` (artifact a1e5a7a3), not re-hashed.


## pytest summary (env infantcat, python 3.13.15, `PYTHONPATH=src python -m pytest tests -q`)
* **101 passed, 1 failed, 29 skipped** (6.6 s) with the real v1.2.1 package unpacked under `data/inputs/data_package`.
  * New tests: `test_models_host.py` (7), `test_make_version.py` (3), `test_apply_findings.py` (6), `test_ingest_issues.py` (1),
    `test_harvest_lib_import.py` (1); `test_inputs_hashes.py` gained the groups/skill-null shape checks and the v1.2.1 requirement.
  * Skipped: 28 data-input hash tests (inputs not materialised in the sandbox — `data_package_v1.2.1.zip` WAS materialised and its
    hash test **passed**), 1 validator-sync test (needs `CATALOG_SKILL_KERNEL`).
  * **Failed: `test_build_determinism.py`** — not a determinism regression: `site_generator/gen/build_site.py` (v2, owned by the
    site track) refuses the v1.2.1 package twice over: (a) README heading "v1.2.0" ≠ VERSION.json 1.2.1 (data-track defect, see
    above); (b) after correcting the heading in a scratch copy it fails with `AttributeError: 'DataFrame' object has no attribute
    'n_samples_x'` — the data track renamed `n_samples_x/_y` → `n_samples_panel/_study` (DATAFIX R3-11) and the v2 generator has not
    been updated yet. The site track's merged `site_generator/` must make this test green; it passed on the 1.2.0 package (67 s) per
    Reviewer 1.
* Every Make target renders under `make -n` (`help`, `unpack` incl. flattening, `package`, `sandpiper-delta`, `install-workflows`).

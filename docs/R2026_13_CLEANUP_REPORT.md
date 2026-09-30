# R2026.13 — cleanup cycle report (package 1.13.0, 2026-09-30)

Owner request: "cleanup mode — all the little things". Fourteen items were listed, answered by the owner on 2026-09-30, and worked
in one wave of leaf agents plus root integration. This note records what landed, what changed in the data, and what is still open.
Numbers come from `build/package/RELEASE_NOTES_R2026.13.md` and `build/gut/gut_scope_summary.json`.

## Headline numbers (1.12.0 → 1.13.0)

| entity | 1.12.0 | 1.13.0 |
|---|---:|---:|
| registry studies | 54,410 | 64,369 (+9,959 newly enumerated ENA studies; host_human yes 6,788 · mixed 235 · unknown 13,665 · no 43,681) |
| catalog studies (`gut_all`) | 2,837 | 2,887 (+50 gap-fill studies) |
| catalog samples | 579,252 | 582,841 |
| sample × field determinations | 3,136,707 | 3,171,459 (R1 2,349,059 · R2 312,078 · R4 260,501 · R3 249,821) |
| catalog runs | 721,678 | 725,603 |
| new fields | — | diet 4,168 samples / 42 studies · smoking_status 4,823 / 20 · medication 3,829 / 42 · stool_consistency_bristol 3,037 / 11 |

Link check: 647,359 internal + 499,107 external links, 0 broken.

## Items and outcomes

1. **Zenodo** — owner enabled the integration on `microbiome_repo-data`; the first DOI is minted by the `data-v1.13.0` Release (check https://zenodo.org/badge/latestdoi/1389758854).
2. **PAT scopes** — Administration + Workflows added by the owner; used for the renames and for installing workflows.
3. **Repository rename** — `infant-gut-catalog` → `microbiome_repo`, `-data`, `-pipeline`; `config/site.yaml` base_url and github.repos updated; RUNBOOK §7 documents redirects and the unchanged local clone names. Incident: installing the workflows pushed to the site repo `main`, whose old trigger deployed a stale 1.2.1 infant build; fixed the same day (`deploy-pages.yml` now runs on `site-v*` tags only; `main` holds `.github/` + README).
4. **Official HDI** — UNDP HDR 2025 statistical annex (owner upload) replaces the transcribed table (`data/inputs/gut/atlas/country_hdi_official.csv`; mean |Δ| 0.015, max 0.048; three band changes GA/NI/TH; no observation conclusion flipped). Atlas now has 18 observation cards incl. lifestyle and collection-year; analyses ship as `scripts/atlas_observations.py` (`make atlas-observations`).
5. **Unlicensed external resources** — kept, with an explicit acknowledgement paragraph on the Sources page.
6. **R3 shard 09 retry** — 107 statements / 39 studies (4 without full text).
7. **Adjudications** — taken by the agent and listed in `docs/OWNER_QUESTIONS_R2026.13.md` ("Decisions I took"); five genuinely undecidable questions remain there.
8. **Registry gap fill** — 9,959 new ENA studies enumerated (blank-taxon slices + named cohorts), 346 rubric-classified, 48 gut candidates + named-cohort verdicts → 50 new catalog studies (4,070 runs / 3,734 BioSamples harvested). Tsimane and RISK are amplicon-only, LifeLines-DEEP is assemblies-only/controlled, Hutterite accession unresolved (see owner questions). Slices are reusable for the monthly cycle (`data/inputs/registry/gapfill/*.py`).
9. **R3b / R4b completion** — R3b 487 studies (incl. 260 infant-extension) → merged 1,296 statements / 745 studies; R4b 62 studies / 7 statements. ~70 studies still blocked by Europe PMC HTTP 500s.
10. **Sandpiper questions** — part sizing was row-based (parts could exceed 90 MB) → `scripts/split_parquet.py` is byte-adaptive; the 2,954 profiled runs "missing" from the wide table belong to BioSamples that are not catalog samples (profiled at run level, no catalog sample row); QC flags are shown, not filtered.
11. **Data quality** — `dq_corrections.parquet` (1,932 rows, 86 studies) applied through the new `--corrections` hook in `build_gut_scope.py`: 35,592 determinations dropped, 457 recoded. Composition: health_condition recode 222 (PRJNA50637 other_cancer → ulcerative_colitis; PRJNA46337 healthy_control → nec), health_condition_detail recode 218 / retire 157, latitude + longitude retire 66 studies (coordinates in another country: Copenhagen for Chinese cohorts, UCSD for US cohorts, sign flips), location_region retire 1,159, location_locality recode 15, lifestyle retire 15 / recode 2, lifestyle_detail retire 12. Age category: study-level fallback now only for single-life-stage studies (PRJNA1306521 children + ≥85 y → unknown). Two DQ leaves (general, coordinates) were refused by the content filter; their scope was covered by the root coordinate check and by the conditions / lifestyle leaves.
12. **Sandpiper history** — not kept in the data repo: assets move to the orphan `release-assets` branch (single commit, force-pushed each release). `registry_runs` is re-written with zstd (128 → 75 MB) to stay one file under GitHub's 100 MB limit.
13. **Vocabularies** — lifestyle 17 codes with new match terms (athletes, herdsmen, space analogue, LTACH, servicemembers, isolated villages); new `diet.yaml`, `smoking.yaml`, `medication.yaml`; `vocab_list` and int-range validation in the scope builder.
14. **Oral scope** — deferred by the owner.

## Open after this cycle

* Owner questions (`docs/OWNER_QUESTIONS_R2026.13.md`): ileal-pouch body site; Hutterite accession; LifeLines-DEEP controlled-access listing; same-country institute coordinates (~300 studies, currently kept); pre-1990 collection-date floor.
* R3b/R4b residue (Europe PMC 500s, ~70 studies); 224 gap-fill studies not judged by the rubric; 2 gap-fill candidates with host unknown.
* Reviewer-model audit of R3/R4 statements; lifestyle / diet / medication via R2 supplementary tables; monthly registry cycle.
* Zenodo DOI display on the site once minted.

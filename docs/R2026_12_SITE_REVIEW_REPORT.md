# R2026.12 / package 1.12.0 — owner site review (2026-09-29)

Every item of the owner's review note (attachment `pasted-text-2026-09-29T05-37-24.txt`) was executed in one wave of
sub-agents and integrated into the pipeline; the release is live (VERSION.json `R2026.12`). Numbers below are read from
`build/gut/gut_scope_summary.json`, `build/package/RELEASE_NOTES_R2026.12.md`, the sub-agent structured outputs and the
built site.

## 1. Review items → what changed

| # | Owner note | Change |
|---|---|---|
| 1 | is the registry all human? | No. The Registry page now leads with the explorer and states the breakdown of the 54,410 screened ENA shotgun-metagenome studies: host human **yes 6,187 · mixed 227 · unknown 7,931 · no 40,065**. The explorer defaults to yes+mixed (checkboxes add unknown / no); the headline number on Home and Registry is the human count (6,414). |
| 2 | trim the catalog numbers on the first page | Five tiles: 2,837 studies · 579,252 samples · 571,857 samples with ≥ 1 curated value · 6,414 registry human studies · 117 countries. |
| 3 | drop field coverage by age category; remove the emphasis on age | Age-coverage table and age tiles removed from Home; age is a normal field on Fields / Samples. |
| 4 | health condition / country widgets janky | Rebuilt as two top-8 bar lists with wide-table counts and explorer-filter links. |
| 5 | search box on top, also for authors | The search box is the first element of Home; it matches studies, cohorts, accessions, **authors** (with study counts) and **collections**. |
| 6 | Registry explorer at the top of Registry | Done; `registry/index.html?study=ACC` now opens and scrolls to the record. |
| 7 | "Every ENA BioProject" | Reworded everywhere: studies are INSDC BioProjects deposited in ENA, NCBI SRA or DDBJ, enumerated through ENA's mirror. |
| 8 | Authors: remove Most-linked; show study previews | Most-linked list removed; a name search shows preview cards (accession, title, samples, country / top condition, year). |
| 9 | Scope → About; Methods there; lab + funder on top | New About section (Scope, Methods, Sources & acknowledgements, Fields, citation); first paragraph names the Olm Lab (https://www.colorado.edu/lab/olm/) and Anthropic's AI for Science program (https://www.anthropic.com/news/ai-for-science-program), both in `config/site.yaml → about`. Old URLs redirect. |
| 10 | combine downloads and releases | One page `downloads/index.html` (package, per-table downloads, release assets, release list, change pages). |
| 11 | core fields: drop antibiotics, add subject_id; add detailed location, lifestyle, collection date | `config/packs/gut.yaml`: `core_fields = [age, sex, country, health_condition, subject_id]`; `key_fields = [detailed_location, lifestyle, collection_date, antibiotic_exposure, bmi, timepoint_label]`. New fields (see §2): `collection_date` (ISO partial / interval), `location_region` / `location_locality` / `location_site` → composed `detailed_location`, `latitude` / `longitude`, `lifestyle` (+ `lifestyle_detail`; vocabulary `config/vocab/lifestyle.yaml`, 17 codes). Site, contribute worklist and explorer read the tiers from the pack. |
| 12 | flag-an-issue too complicated; remove confirm-correct | New one-dropdown + one-text-box form `simple-finding.yml` (accession, release, URL prefilled); "Confirm correct" removed. **Owner action**: copy `site_generator/gen/issue_templates/simple-finding.yml` into the Issues repo's `.github/ISSUE_TEMPLATE/` (the installer's copy list is documented in docs/CONTRIBUTE.md §6). |
| 13 | Registry classification hard to read; registry record link | Study pages: "How this study entered the registry" — one plain sentence plus a compact evidence list; the Registry record button opens the record. |
| 14 | sample click → filtered samples table | `samples/index.html?sample=<key>` filters the table to the sample and opens its panel. |
| 15 | link samples to NCBI / registry | Sample rows and panels link SAMN → NCBI BioSample, SAME → ENA, SAMD → DDBJ, runs → ENA. |
| 16 | depth and instrument per study | Sequencing block on every study page (runs, mean / median Gbp per run, layout, platform / models, Sandpiper share, first_public range) from the new `gut_runs.parquet`; Gbp-per-run column on the studies index. |
| A1 | collections | `config/collections.yaml`: 31 collections (benchmark 5, population 4, lifestyle 6, design 6, disease 8, age 3), each with member studies and/or explorer filters; pages `collections/` with build-time counts; `samples/index.html?collection=<id>` applies the rule in the explorer. |
| A2 | interesting observations (microbiome-atlas style) | Atlas section: taxon world map (7,992 taxa × 101 countries, D3 choropleth / globe, per-study dossiers) and 14 study-aware observation cards with figures and CSVs (`atlas/observations.html`). |
| A3 | interactive PCA on Sandpiper | Sandpiper 2.0.0 profiles joined for the whole catalog (372,911 runs → 339,626 samples, 2,084 studies); genus-level CLR-PCA of 335,956 samples × 383 genera (PC1–5: 16.3 / 6.5 / 3.8 / 3.2 / 2.3 %); interactive Canvas scatter `atlas/pca.html` (colour by age, country, condition, lifestyle, study, top genus; hover → sample / study links). |

## 2. New fields — routes and coverage (579,252 samples)

| field | samples | studies | R1 (attributes) | R3 (full text) | R4 (abstract / description) |
|---|---|---|---|---|---|
| collection_date | 340,455 (58.8 %) | 2,016 | 321,972 | 15,864 | 2,619 |
| detailed_location | 251,205 (43.4 %) | 1,763 | — composed — | | |
| location_region | 205,394 (35.5 %) | | 192,908 | 9,318 | 3,168 |
| location_locality | 144,242 (24.9 %) | | 120,914 | 17,032 | 6,296 |
| location_site | 56,567 (9.8 %) | | 7,093 | 34,977 | 14,497 |
| latitude / longitude | 253,651 (43.8 %) | 1,527 | 253,651 | | |
| lifestyle | 10,658 (1.8 %) | 82 | 1,775 | 3,329 | 5,554 |

Lifestyle codes (samples): rural_non_industrialized 3,862 · institutionalized 1,944 · urban_industrialized 1,813 · athlete 691 · military 508 · other_lifestyle 427 · vegetarian_or_vegan 357 · transitional_or_migrant 306 · indigenous_community 235 · extreme_environment 175 · hunter_gatherer 137 · traditional_agriculturalist 103 · pastoralist 88 · spaceflight_or_analog 12.

* **R1** (`catalog.scopes.newfields_r1`, 1,153,739 rows): deterministic date parser (only the `collection_date` key occurs; formats and rejects tabulated in docs/GUT_NEWFIELDS_R1_REPORT.md), lat/lon parser (40 swapped pairs rejected; 13,870 country mismatches kept at confidence 0.7), 1,281 distinct location strings normalised by the utility model into region / locality / site with a substring / exonym guard (map: `data/inputs/gut/gut_location_map.parquet`, 1,140 mapped), admin-1 region reverse-geocoded from coordinates for 124,272 samples at confidence 0.6 (GeoNames cities1000; locality never filled from coordinates). Lifestyle only from attribute keys that state it (never ethnicity).
* **R3b** (24 shards, 1,317 full-text studies, 1,180 with XML): 1,034 replicated, quote-verified cohort statements over 598 studies; 861 single-replicate statements and 1,252 subgroup statements kept aside (`data/inputs/gut/r3b/`). Two shards were stopped by a content-safety refusal of the agent's own turn and re-run successfully with a no-echo rule. Leaves shrank the text chunk (15–28 k chars instead of 36 k) to stay under the per-frame token ceiling — Results sections were mostly truncated, so the counts are lower bounds. `temperature=0` is rejected by the rubric model; replicates differ by system preamble only.
* **R4b** (6 shards, 2,837 studies incl. the 389 infant-extension studies): 546 study-level statements over 338 studies (abstract 0.5 / description 0.45 / title 0.4). Shard 0 and 1 hit the token ceiling with 42 and 20 studies unprocessed.

Determinations 1,861,883 → 3,136,707 (R1 2,326,949 · R2 312,314 · R4 261,908 · R3 235,536). No pre-existing field changed value (release notes: Δ n = 0 for age, sex, country, health condition, subject, antibiotics, BMI, timepoint).

## 3. Sandpiper for the whole catalog

One streaming pass over the 3.7 GB Sandpiper 2.0.0 bulk file (GTDB R232) recovered all 372,911 profiled gut runs (76.5 M rows); 2,954 runs have no catalog sample key. Tables: `gut_sandpiper_sample_summary` (339,626 samples; 41,947 carry a QC flag — flagged, never dropped), `gut_sandpiper_pca_scores/_loadings/_variance`, `gut_sandpiper_study_coverage`; the genus (185 MB) and species (199 MB) long tables are release assets in < 100 MB parts (`assets/gut_sandpiper_sample_{genus,species}_v1.12.0_part*.parquet`). CLR-PCA vs Hellinger / Bray-Curtis PCoA on 20,000 samples: axis 1 agrees (|r| 0.85–0.86), axis 2 only moderately (0.52–0.59). Report: `GUT_SANDPIPER_REPORT.md` (in the package).

## 4. Caveats the owner should know

* **HDI table transcribed, unverified.** hdr.undp.org is not reachable from the sandbox; the 96 country HDI values behind the industrialisation-gradient cards and the VANISH/BloSSUM volcano were written from memory (2 decimals) and are labelled as such on the page. Replace `data/inputs/gut/atlas/country_hdi.csv` with the official CSV and rebuild.
* **Collections that could not be populated**: Tsimane, Hutterite / Amish, LifeLines-DEEP (EGA), and several benchmark deposits are not in the catalog (the candidates checked were amplicon, non-human or controlled access); lifestyle-based collections list studies explicitly and also filter on the new column.
* **Registry non-human studies** remain in `registry_studies` (40,065 `host_human = no`); the site now says so and hides them by default.
* **Front-end code** (atlas.js, pca.js, explorer collection filter) was verified structurally and by the Actions Playwright smoke test only; the globe toggle and the lasso were not exercised in a browser here.
* **Issue form**: `simple-finding.yml` must be installed in the Issues repo by the owner (PAT lacks Workflows/Administration).
* Infant-extension studies received lifestyle / location / date statements only from abstracts (R4b); their full texts were not re-read.
* Site size 693 MB (Pages limit 1 GB); package zip 158 MB (served from the GitHub Release, > 90 MiB guard).

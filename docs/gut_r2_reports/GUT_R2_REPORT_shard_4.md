# GUT R2 deterministic supplementary-table extraction — shard 4 of 8

Scope: 165 non-infant human-gut shotgun studies with ≥ 1 open-access PMC paper (214 distinct PMCIDs, ≤ 4 own-data papers per study).
Method: pipeline R2 (microbiome_repo-pipeline `gapfill_samples.r2_gate` / `r2_extract` logic re-hosted on the pmcid input instead of `study_paper_links.csv`; `_supp_id_columns`, `norm_key`, `q12`, `DET_COLS` and `r1_parsers` imported unchanged). Exact-ID gate on the study's ENA universe (BioSample, secondary sample, run, experiment, library_name, sample_title); matrix sheets excluded; header-named columns only; parsers deterministic. **No LLM calls were made.**
Deliverables: `gut_r2_determinations_shard_4.parquet` (determination schema of config/packs/gut.yaml, src_track gut_all_v1, release R2026.7, package 1.8.0), `gut_r2_gate_shard_4.parquet`, `gut_supp_header_map_shard_4.csv`, `gut_r2_log_shard_4.json`, plus `gut_r2_conflicts_shard_4.csv` and `gut_r2_skipped_headers_shard_4.csv`.

## Fetch (Europe PMC `supplementaryFiles`, ≤ 2 concurrent, `includeInlineImage=false`, streamed with an 80 MB / 240 s cap, then a 400 MB / 600 s retry for the capped ones)
| outcome | PMCIDs |
|---|---|
| zip | 180 |
| not open access | 19 |
| no supplementary files | 14 |
| ERR size_cap after 419430584 bytes | 1 |

* Studies with ≥ 1 supplementary zip: **141 / 165**; 61 of those zips held no xlsx/xls/csv/tsv/txt table.
* HTTP 500 / 429 / connection errors after 2 attempts: 0 (none observed as persistent 500s in this shard; 19 PMCIDs are not open access at Europe PMC and 14 have no supplementary files).
* 1 PMCID (PMC11315937) exceeded the 400 MB cap and was not read.

## Gate
* Sheets read: 1046; sheets passing the exact-ID gate (≥ 50 % of rows or ≥ 20 exact hits): 66 in **24 studies**; of these 15 were matrix-shaped (ids in header, numeric body) and excluded.
* Gate-passing sheets with ≥ 1 header-named pack-field column and a single id column (`r2_usable`): **34 sheets in 19 studies**.
* Gate variant `prefix_stripped` (sample_title / library_name after removing the study-wide common prefix, tried only when the raw gate fails; confidence 0.8): 9 passing sheets, 934 rows. Bare-number ids (e.g. `LS_34` → `34`) are matched column-wise only, in an id-like headed column with ≥ 80 % of the column matching.
* Transposed metadata sheets (samples as columns, attributes as rows — e.g. mBio `metadata` sheets) are detected when ≥ 20 header cells are exact ids and the body is not a numeric matrix; they are transposed before gating (0 sheets).
* Studies with a zip but no gate pass: 51 with 0 exact hits in any sheet, 5 with 1–19 hits only (near misses: PRJEB13830 (max 11), PRJEB29060 (max 12), PRJEB47909 (max 1), PRJNA434731 (max 12), PRJNA646512 (max 14)).

## Rows
Total **5201 rows** over **1521 samples** in 17 studies (one row per sample × field; confidence 0.85 raw join, 0.8 prefix-stripped join).

| field | rows | samples | studies | conf 0.85 | conf 0.80 |
|---|---|---|---|---|---|
| sex | 1170 | 1170 | 11 | 1009 | 161 |
| age_at_collection_days | 1118 | 1118 | 9 | 976 | 142 |
| health_condition_detail | 1017 | 1017 | 9 | 884 | 133 |
| bmi | 731 | 731 | 5 | 708 | 23 |
| subject_id | 439 | 439 | 5 | 306 | 133 |
| timepoint_label | 416 | 416 | 6 | 302 | 114 |
| antibiotic_exposure | 196 | 196 | 2 | 82 | 114 |
| country | 114 | 114 | 1 | 0 | 114 |

Per study:

| study | rows | samples covered | samples in study | fields | PMCIDs |
|---|---|---|---|---|---|
| PRJEB21528 | 1456 | 385 | 385 | age_at_collection_days,bmi,health_condition_detail,sex | PMC10782949 |
| PRJEB29127 | 684 | 171 | 171 | age_at_collection_days,bmi,health_condition_detail,sex | PMC12341127 |
| PRJEB77410 | 117 | 41 | 41 | age_at_collection_days,health_condition_detail,sex | PMC12980963 |
| PRJEB86846 | 57 | 19 | 19 | health_condition_detail,sex,subject_id | PMC12323421 |
| PRJNA1030952 | 51 | 51 | 51 | health_condition_detail | PMC11446047 |
| PRJNA1364832 | 258 | 129 | 129 | subject_id,timepoint_label | PMC13408661 |
| PRJNA1475610 | 410 | 82 | 82 | age_at_collection_days,antibiotic_exposure,bmi,health_condition_detail,sex | PMC13522148 |
| PRJNA528960 | 70 | 35 | 133 | subject_id,timepoint_label | PMC7890861 |
| PRJNA531203 | 31 | 31 | 31 | sex | PMC7141701 |
| PRJNA645402 | 99 | 33 | 33 | age_at_collection_days,sex,timepoint_label | PMC7683401 |
| PRJNA647720 | 86 | 86 | 86 | timepoint_label | PMC8546969 |
| PRJNA660443 | 23 | 23 | 70 | health_condition_detail | PMC11109446 |
| PRJNA680579 | 19 | 19 | 19 | timepoint_label | PMC8327913 |
| PRJNA905467 | 568 | 142 | 142 | age_at_collection_days,bmi,sex,subject_id | PMC10825054 |
| PRJNA939026 | 79 | 28 | 28 | age_at_collection_days,bmi,sex | PMC10673896 |
| PRJNA948536 | 798 | 114 | 114 | age_at_collection_days,antibiotic_exposure,country,health_condition_detail,sex,subject_id,timepoint_label | PMC10865789 |
| PRJNA954584 | 395 | 132 | 132 | age_at_collection_days,health_condition_detail,sex | PMC10668026 |

### Conflicts
171 (sample, field) conflicts between sheets; resolved by keeping the sheet with more exact-ID hits and logged in `gut_r2_conflicts_shard_4.csv`:
* PRJEB21528 · health_condition_detail: kept `paper.supp.spectrum.01050-23-s0001.xlsx[S.Table1!group]` over `paper.supp.spectrum.02182-24-s0001.xlsx[table1!Disease]` (171 samples)

Note: PRJEB21528 is labelled `HC` by one re-analysis paper and `ACVD` by another for the same 171 BioSamples — a genuine cross-paper disagreement that should go to the curator queue rather than be trusted at 0.85.

## Header map (`gut_supp_header_map_shard_4.csv`, 24 header forms actually met in usable sheets)
Started from `config/attribute_field_map.csv` (norm_key lookups) and extended by regex families: bare `Age` = years unless an `age_unit(s)` column exists (values > 120 or median < 1 → skipped as implausible years; ranges like `80-99`, `<70` never become values); `age_<unit>` headers use the header unit; `sex`/`gender` (+ header codebooks such as `Gender (1:male, 2:female)`); `BMI` numeric 10–80 (categories such as `NW` skipped); `country`/`geographic location` via pycountry; antibiotic exposure headers with ≥ 80 % yes/no-parsable values (class columns `<class>_antibiotic`, ARG accessions, days/dose/name columns skipped); subject/patient/participant/individual identifiers; timepoint/visit/day/week labels (≤ 60 distinct); disease/diagnosis/group/status/condition/phenotype → `health_condition_detail` raw text (≤ 30 distinct, non-numeric, median length ≥ 3; one column per sheet by priority diagnosis > disease > … > group).

| header_norm | field | parser | sheets | values | parsed |
|---|---|---|---|---|---|
| age | age_at_collection_days | age_bare_adult_years | 27 | 7174 | 1667 |
| antibiotic_exposure | antibiotic_exposure | categorical_yesno | 2 | 164 | 164 |
| recentabx_binary | antibiotic_exposure | categorical_yesno | 2 | 228 | 228 |
| bmi | bmi | bmi_numeric | 9 | 1557 | 1557 |
| geographic_location | country | country | 2 | 228 | 228 |
| group | health_condition_detail | raw_text | 8 | 836 | 836 |
| disease | health_condition_detail | raw_text | 7 | 11867 | 11867 |
| diagnosis | health_condition_detail | raw_text | 4 | 684 | 684 |
| health_status | health_condition_detail | raw_text | 2 | 46 | 46 |
| host_phenotype | health_condition_detail | raw_text | 2 | 228 | 228 |
| condition | health_condition_detail | raw_text | 2 | 38 | 38 |
| disease_status | health_condition_detail | raw_text | 2 | 262 | 262 |
| sex | sex | categorical_sex | 7 | 491 | 488 |
| gender | sex | categorical_sex | 5 | 1056 | 1056 |
| gender_1_male_2_female | sex | categorical_sex | 4 | 684 | 684 |
| gender_m_f | sex | categorical_sex | 2 | 62 | 62 |
| patient | subject_id | identifier | 2 | 70 | 70 |
| patientnumber | subject_id | identifier | 2 | 228 | 228 |
| subject_id | subject_id | identifier | 2 | 38 | 38 |
| participant_id | subject_id | identifier | 2 | 258 | 258 |
| subject | subject_id | identifier | 2 | 284 | 284 |
| timepoint | timepoint_label | label | 4 | 281 | 281 |
| day | timepoint_label | label | 3 | 205 | 205 |
| visit | timepoint_label | label | 2 | 70 | 70 |

## Top skipped headers in gate-passing, non-matrix sheets (≤ 40 columns) — `gut_r2_skipped_headers_shard_4.csv` (469 distinct)
| header_norm | sheets | reason |
|---|---|---|
| id | 7 | ambiguous/fixed skip |
| sample | 6 | ambiguous/fixed skip |
| xu_metaphlan_pcoa_1 | 6 | not a pack field header |
| xu_metaphlan_pcoa_2 | 6 | not a pack field header |
| xu_bracken_pcoa_1 | 6 | not a pack field header |
| xu_bracken_pcoa_2 | 6 | not a pack field header |
| true_label | 4 | not a pack field header |
| sampleid | 4 | not a pack field header |
| weight_kg | 3 | not a pack field header |
| smoking | 3 | not a pack field header |
| q30 | 2 | not a pack field header |
| n50 | 2 | not a pack field header |
| phylum_statistic | 2 | not a pack field header |
| class_statistic | 2 | not a pack field header |
| order_statistic | 2 | not a pack field header |
| family_statistic | 2 | not a pack field header |
| genus_statistic | 2 | not a pack field header |
| species_statistic | 2 | not a pack field header |
| marital_status | 2 | not a pack field header |
| dwelling_condition | 2 | not a pack field header |
| education_level | 2 | not a pack field header |
| sample_center | 2 | not a pack field header |
| group [secondary health column; kept diagnosis] | 2 | secondary health column; kept diagnosis |
| height_cm | 2 | not a pack field header |
| body_temperature | 2 | not a pack field header |
| pulse_c_p_m | 2 | not a pack field header |
| breathe_c_p_m | 2 | not a pack field header |
| systolic_pressure_mmhg | 2 | not a pack field header |
| diastolic_pressure_mmhg | 2 | not a pack field header |
| staple_food_structure | 2 | not a pack field header |
| frequency_of_eating_vegetables | 2 | not a pack field header |
| frequency_of_eating_ivestock_meat | 2 | not a pack field header |
| frequency_of_eating_poultry | 2 | not a pack field header |
| frequency_of_eating_nutrient_supplements | 2 | not a pack field header |
| frequency_of_drinking_yogurt_or_probiotic_drinks | 2 | not a pack field header |
| in_the_past_six_months_exposure_to_secondhand_smoke_situation | 2 | not a pack field header |
| tryptophane_m | 2 | not a pack field header |
| glutamic_acid_m | 2 | not a pack field header |
| tyrosine_m | 2 | not a pack field header |
| phenylalanine_m | 2 | not a pack field header |

Ambiguous by design (listed, not extracted): `id`/`sample`/`sampleid` (id columns), `age_group`/`age_category`, `treatment`/`treatment_group`, `variant` (CONTROL/CVID in PRJNA666684), `pathogen`, `abxdaysprior6months` (days, not yes/no), `weight_kg`/`height_cm`/`smoking`/`marital_status`/diet frequencies (pack future_fields or out of pack).

## Deviations
* PMC11315937 (one of 214 PMCIDs) not read: supplementary zip > 400 MB. Three other zips (140–190 MB) were read after a second pass with the larger cap.
* Fetching used a streaming variant of `harvest_lib.fetch` (same cache schema, 2 attempts, `includeInlineImage=false`) because the library's 5-retry loop on HTTP 500 and unbounded body size did not fit the time-box; results are cached under `CATALOG_CACHE_DIR` in the workspace and keyed by the canonical `…/supplementaryFiles` URL.
* No LLM calls.

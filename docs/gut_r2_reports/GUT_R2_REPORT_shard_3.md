# GUT R2 deterministic supplementary-table extraction — shard 3

Generated 2026-09-28T04:28:03Z. Scope `gut_all`, src_track `gut_all_v1`, release R2026.7 / package 1.8.0. Method: microbiome_repo-pipeline `gapfill_samples` R2 gate (exact-ID ≥ 50 % of rows or ≥ 20 hits; matrix sheets excluded) + header-named columns, deterministic parsers only (no LLM calls).

## Coverage

- studies in shard: **165**; PMCIDs: 226
- full-text XML status counts: {'200': 203, 'ERR': 23}
- supplementary-zip fetch status counts (attempted 226 of 226 PMCIDs): {'200': 135, 'skipped_no_tabular_supp': 91}
- PMCIDs whose zip fetch was NOT attempted within the time-box: 0
- studies with ≥ 1 readable supplementary zip: **86**
- studies with ≥ 1 gate-passing, header-named (r2_usable) sheet: **21**
- studies with ≥ 1 determination row: **18**
- sheets gated: 1580; passing exact gate: 135 (raw: 80, prefix_stripped: 55); r2_usable: 45
- determination rows: **11602**; conflicts logged (differing values across sheets, resolved by more exact hits): **341**

## Rows and samples per field

| field | rows | samples |
|---|---:|---:|
| age_at_collection_days | 1684 | 1684 |
| sex | 1775 | 1775 |
| bmi | 1783 | 1783 |
| country | 785 | 785 |
| health_condition_detail | 725 | 725 |
| antibiotic_exposure | 482 | 482 |
| subject_id | 3839 | 3839 |
| timepoint_label | 529 | 529 |

## Per-study rows

| study | rows | samples | fields |
|---|---:|---:|---|
| PRJEB47976 | 195 | 65 | age_at_collection_days, health_condition_detail, sex |
| PRJEB58436 | 1290 | 430 | age_at_collection_days, bmi, sex |
| PRJEB60398 | 3108 | 3108 | subject_id |
| PRJEB76817 | 770 | 263 | bmi, subject_id, timepoint_label |
| PRJEB86834 | 16 | 10 | age_at_collection_days, sex |
| PRJNA1438274 | 106 | 53 | age_at_collection_days, sex |
| PRJNA1474380 | 55 | 55 | subject_id |
| PRJNA447983 | 559 | 113 | age_at_collection_days, bmi, country, health_condition_detail, sex |
| PRJNA449784 | 1161 | 292 | age_at_collection_days, bmi, health_condition_detail, sex |
| PRJNA561510 | 110 | 22 | age_at_collection_days, bmi, country, health_condition_detail, sex |
| PRJNA797994 | 650 | 650 | country |
| PRJNA802048 | 180 | 180 | subject_id |
| PRJNA809514 | 72 | 36 | age_at_collection_days, bmi |
| PRJNA811494 | 225 | 75 | age_at_collection_days, bmi, sex |
| PRJNA828396 | 1389 | 233 | age_at_collection_days, bmi, health_condition_detail, sex, subject_id, timepoint_label |
| PRJNA834885 | 33 | 33 | timepoint_label |
| PRJNA861716 | 1436 | 359 | age_at_collection_days, antibiotic_exposure, bmi, sex |
| PRJNA947377 | 247 | 124 | antibiotic_exposure, sex |

## Header map

3582 distinct normalised headers met in gate-passing sheets; 34 mapped to a pack field (see gut_supp_header_map_shard_3.csv).

## Top skipped headers (ambiguous — listed, not extracted)

| header_norm | reason | n columns |
|---|---|---:|
| group | ambiguous: generic group header, no health-vocabulary value | 6 |
| hiv_status | ambiguous: not header-named for a single field | 2 |
| percentage_of_input_merged | ambiguous: not header-named for a single field | 1 |
| percentage_of_input_non_chimeric | ambiguous: not header-named for a single field | 1 |
| percentage_of_input_passed_filter | ambiguous: not header-named for a single field | 1 |
| oral_sex | ambiguous: not header-named for a single field | 1 |
| trigger_abx_indications | ambiguous: not header-named for a single field | 1 |
| trigger_abx | ambiguous: not header-named for a single field | 1 |
| years_since_diagnosis | ambiguous: not header-named for a single field | 1 |
| study_group | ambiguous: generic group header, no health-vocabulary value | 1 |
| status | ambiguous: not header-named for a single field | 1 |
| smoking_status_1 | ambiguous: not header-named for a single field | 1 |
| smoking_status | ambiguous: not header-named for a single field | 1 |
| sexual_orientation | ambiguous: not header-named for a single field | 1 |
| candida_group | ambiguous: not header-named for a single field | 1 |
| cage_id | ambiguous: not header-named for a single field | 1 |
| cdi_abx | ambiguous: not header-named for a single field | 1 |
| ajcc_stage | ambiguous: not header-named for a single field | 1 |
| age_of_onset | ambiguous: not header-named for a single field | 1 |
| inflammatory_bowel_disease | ambiguous: not header-named for a single field | 1 |
| fecal_metagenome_ncbi_biosample | ambiguous: not header-named for a single field | 1 |

## Deviations

- Supplementary zips were fetched only for the 135 of 226 PMCIDs whose Europe PMC full-text XML lists >= 1 tabular/archive supplementary file (xlsx/xls/csv/tsv/txt/zip) or whose full-text XML was unavailable (HTTP error); the 91 PMCIDs whose full text lists only non-tabular supplements (docx/pdf/images) were not fetched (zip_status 'skipped_no_tabular_supp' in the log).
- Exact-ID universe excludes bare numbers, tokens < 3 characters and values shared by > 1 BioSample (e.g. PRJNA797994 integer library names); studies whose only per-sample identifiers are bare integers cannot be joined by this deterministic gate.
- Files > 60 MB inside a zip (3) and sheets > 200,000 rows (truncated to the first 200,000) were not fully read.
- Header-named health_condition_detail columns with generic headers (group / cohort / condition ...) were extracted only when >= 1 value carries a health_conditions.yaml match term or healthy/control/patient/case token; 'category'/'status'/'classification' headers were never used.
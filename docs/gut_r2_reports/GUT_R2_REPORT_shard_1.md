# GUT R2 deterministic supplementary-table extraction — shard 1

Scope `gut_all`, route R2, `determined_by = gut_r2_header_named`, src_track `gut_all_v1`, release R2026.7 / package 1.8.0. No LLM calls.

## Coverage

| metric | value |
|---|---|
| studies in shard | 165 |
| PMCIDs in shard | 228 |
| PMCID fetch outcomes | {"200": 228} |
| studies with ≥ 1 supplementary zip | 165 |
| table sheets read | 1128 |
| sheets passing the exact-ID gate | 71 |
| sheets passing only the prefix-stripped variant gate (conf 0.8) | 0 |
| matrix sheets excluded | 11 |
| r2_usable sheets (gate pass, not matrix, ≥ 1 header-named field column) | 25 |
| studies with ≥ 1 gate-passing usable sheet | 13 |
| studies with ≥ 1 determination row | 12 |
| determination rows | 3836 |
| confidence distribution | {"0.85": 3836} |
| conflicts logged (kept sheet with more exact hits / intra-sheet ambiguity dropped) | 119 {"cross_column_same_sheet": 66, "cross_sheet": 53} |
| unreadable / skipped members | {"unreadable": 30, "bad zip": 21, "empty or single column": 21, "skipped": 1} |

## Rows and samples per field

| field | rows | samples | studies |
|---|---|---|---|
| age_at_collection_days | 633 | 633 | 5 |
| bmi | 361 | 361 | 2 |
| country | 209 | 209 | 1 |
| health_condition_detail | 566 | 566 | 5 |
| sex | 1814 | 1814 | 7 |
| subject_id | 69 | 69 | 1 |
| timepoint_label | 184 | 184 | 3 |

## Header map (headers that produced rows or were mapped in usable sheets)

| header_norm | field | parser | reason | sheets | values | parsed |
|---|---|---|---|---|---|---|
| age | age_at_collection_days | age_numeric | attribute_field_map.csv; bare age header = years (adult rule) | 7 | 1440 | 1061 |
| age_years | age_at_collection_days | age_numeric | attribute_field_map.csv | 3 | 731 | 731 |
| age_year | age_at_collection_days | age_numeric | age_with_unit_in_header | 1 | 99 | 99 |
| bmi | bmi | bmi_numeric | bmi_header | 3 | 676 | 676 |
| geo_loc_name_country | country | country | country_header | 1 | 209 | 209 |
| geo_loc_name | country | country | attribute_field_map.csv | 1 | 209 | 209 |
| group | health_condition_detail | raw_text | condition_header | 6 | 235 | 235 |
| type | health_condition_detail | raw_text | condition_header | 3 | 357 | 357 |
| groups | health_condition_detail | raw_text | condition_header | 2 | 224 | 224 |
| disease_state | health_condition_detail | raw_text | condition_header | 1 | 87 | 87 |
| sex | sex | categorical_sex | attribute_field_map.csv | 6 | 1776 | 1731 |
| gender | sex | categorical_sex | attribute_field_map.csv | 6 | 1554 | 1554 |
| individual | subject_id | identifier | subject_header | 1 | 69 | 69 |
| visit | timepoint_label | label | attribute_field_map.csv | 1 | 32 | 32 |
| day | timepoint_label | label | timepoint_header | 1 | 69 | 69 |
| timepoint | timepoint_label | label | attribute_field_map.csv | 1 | 83 | 83 |

## Top skipped headers in gate-passing sheets (unmapped or ambiguous)

| header_norm | reason | sheets |
|---|---|---|
| weight | unmapped | 5 |
| unnamed | unmapped | 3 |
| family_disease | unmapped | 2 |
| genes | unmapped | 2 |
| shannon | unmapped | 2 |
| cluster | unmapped | 2 |
| diagnosis_age | unmapped | 2 |
| label | unmapped | 2 |
| family_member | unmapped | 2 |
| mds1 | unmapped | 2 |
| mds2 | unmapped | 2 |
| family_history_disease | unmapped | 2 |
| reads | unmapped | 2 |
| last_antibiotics_course | unmapped | 2 |
| antibiotics_course | unmapped | 2 |
| vaccination_3years | unmapped | 2 |
| birds_exposure | unmapped | 2 |
| pets_exposure | unmapped | 2 |
| cattle_exposure | unmapped | 2 |
| animal_exposure_current | unmapped | 2 |
| markers | unmapped | 2 |
| waz | unmapped | 2 |
| vegetarian | unmapped | 2 |
| delivery_mode_factor | unmapped | 2 |
| frequent_meat | unmapped | 2 |
| sample_id_2 | unmapped | 2 |
| eat_visceral_organs | unmapped | 2 |
| visceral_organs | unmapped | 2 |
| igapos_bacteria | unmapped | 2 |
| home_room_factor | unmapped | 2 |
| teff_freq_factor_binary | unmapped | 2 |
| latrine_in_room_factor | unmapped | 2 |
| breast_18m_factor | unmapped | 2 |
| whz | unmapped | 2 |
| hp_result | unmapped | 2 |
| sour_milk | unmapped | 2 |
| flag | unmapped | 2 |
| bmiz | unmapped | 2 |
| ibd | unmapped | 2 |
| stunting | unmapped | 2 |

## Studies with usable sheets

| study | pmcid | file | sheet | id column | exact hits | variant hits | header-named columns |
|---|---|---|---|---|---|---|---|
| PRJEB36140 | PMC13505095 | 12967_2026_8269_MOESM4_ESM.xlsx | S1 | Bio_sample_id | 166 | 0 | Group->health_condition_detail;Timepoint->timepoint_label;Type->health_condition_detail |
| PRJEB6337 | PMC10972203 | metabolites-14-00132-s001.zip::SupplementaryTable. | Supplementary Table S1 | sample.ID | 241 | 0 | type->health_condition_detail;Gender->sex |
| PRJNA1033539 | PMC10679412 | Table_1.XLSX | supplemental Table 1 | ID | 124 | 0 | Group->health_condition_detail |
| PRJNA1033539 | PMC10679412 | Table_2.XLSX | Bray_Curtis | ID | 124 | 0 | Group->health_condition_detail |
| PRJNA1033539 | PMC10679412 | Table_2.XLSX | jaccard-Curtis | ID | 124 | 0 | Group->health_condition_detail |
| PRJNA1071720 | PMC13376552 | 41467_2026_73290_MOESM4_ESM.zip::Source Data Figur | Figure-7A Cohort study 2 | Run | 836 | 0 | geo_loc_name_country->country;geo_loc_name->country |
| PRJNA1203401 | PMC11827547 | LIV-45-0-s002.xlsx | data | study.id | 132 | 0 | study.id->subject_id;sex->sex;age->age_at_collection_days;bmi->bmi |
| PRJNA1261967 | PMC12241578 | 41467_2025_61161_MOESM6_ESM.xlsx | Fig. 1F | SampleID | 112 | 0 | Groups->health_condition_detail |
| PRJNA1261967 | PMC12241578 | 41467_2025_61161_MOESM6_ESM.xlsx | Fig. 1G | SampleID | 112 | 0 | Groups->health_condition_detail |
| PRJNA1261967 | PMC12241578 | 41467_2025_61161_MOESM6_ESM.xlsx | Fig. 4I | SampleID | 32 | 0 | Visit->timepoint_label |
| PRJNA1345963 | PMC12963580 | 42003_2026_9639_MOESM2_ESM.zip::Supplementary_Data | F1a-d, FS1a,c-i | sample-id | 104 | 0 | Sex->sex;Age_Years->age_at_collection_days |
| PRJNA1345963 | PMC12963580 | 42003_2026_9639_MOESM2_ESM.zip::Supplementary_Data | F1e, FS1k | sample-id | 104 | 0 | Age_Years->age_at_collection_days |
| PRJNA1345963 | PMC12963580 | 42003_2026_9639_MOESM2_ESM.zip::Supplementary_Data | FS2f-g | sample_name | 100 | 0 | Sex->sex;Age_Years->age_at_collection_days |
| PRJNA608678 | PMC8931321 | pnas.2121180119.sd01.xlsx | A | Sample Name | 69 | 0 | Individual->subject_id;Day->timepoint_label;Age->age_at_collection_days;Sex->sex |
| PRJNA668607 | PMC8407408 | msystems.00889-21-st001.xlsx | Table S1 | Accession number | 51 | 0 | Type->health_condition_detail |
| PRJNA686265 | PMC8357928 | 41467_2021_25213_MOESM3_ESM.xlsx | 300FG Tanzania Metadata | PID | 316 | 0 | Gender->sex;Age->age_at_collection_days;BMI->bmi |
| PRJNA686265 | PMC8357928 | 41467_2021_25213_MOESM19_ESM.xlsx | Fig. 1a | PID | 316 | 0 | Gender->sex;Age->age_at_collection_days |
| PRJNA686265 | PMC8357928 | 41467_2021_25213_MOESM19_ESM.xlsx | Fig. 1c | Sample | 315 | 0 | Gender->sex;Age->age_at_collection_days |
| PRJNA686265 | PMC8357928 | 41467_2021_25213_MOESM19_ESM.xlsx | Fig. 2d | unnamed | 315 | 0 | Gender->sex;Age->age_at_collection_days;BMI->bmi |
| PRJNA688881 | PMC8265136 | 12916_2021_2034_MOESM4_ESM.xlsx | Table s-2 | Sample ID | 99 | 0 | Age(year)->age_at_collection_days;Gender->sex |
| PRJNA688881 | PMC8265136 | 12916_2021_2034_MOESM4_ESM.xlsx | Table s-3 | Sample ID | 99 | 0 | Group->health_condition_detail |
| PRJNA688881 | PMC8265136 | 12916_2021_2034_MOESM4_ESM.xlsx | Table s-6 | Sample ID | 117 | 0 | Disease state->health_condition_detail |
| PRJNA688881 | PMC8265136 | 12916_2021_2034_MOESM4_ESM.xlsx | Table s-1 | Sample ID | 53 | 0 | Group->health_condition_detail |
| PRJNA784939 | PMC12121241 | 12967_2025_6404_MOESM1_ESM.zip::Table S1.xlsx | Table S1 | RunID | 971 | 0 | Sex->sex |
| PRJNA919082 | PMC12955388 | spectrum.00706-25-s0001.xlsx | TABLE S1 | unnamed | 64 | 0 | Sex->sex;Age->age_at_collection_days |

## Method

1. Supplementary zips fetched through `harvest_lib.fetch` (Europe PMC `supplementaryFiles`), 2 concurrent workers, `max_retries=2` with exponential backoff on 429/5xx, workspace cache `r2cache/`.
2. Every xlsx/xls/csv/tsv/txt member (one level of nested zips) read with `header=None, dtype=str` (≤ 60k rows, ≤ 60 sheets, ≤ 60 MB per member); header row picked by `gapfill_samples._supp_id_columns`.
3. Exact-ID gate (pipeline rule): distinct cells equal to a BioSample / secondary sample / run / experiment accession, library_name or sample_title of the study ≥ 20 or ≥ 50 % of rows; matrix sheets (ids in header, > 20 numeric columns) excluded. Variant gate: same rule on sample_title / library_name after stripping the study-wide common prefix, tried only when the raw gate fails (confidence 0.8).
4. Header-named columns only: `attribute_field_map.csv` (pack fields, deterministic parsers) + the regex header rules in `gut_r2_shard.py`; parsers from `r1_parsers` (age units, sex, yes/no incl. drug-name→yes, country, numeric). Bare `Age` = years (adult rule); ranges/thresholds are never ages; BMI 10–80; condition headers (`disease`/`diagnosis`/`group`/`status`…) taken as raw text only when low-cardinality and non-numeric.
5. One row per (sample, field); intra-sheet disagreement for the same sample drops the value (logged), cross-sheet disagreement keeps the sheet with more exact hits (logged).

## Caveats for downstream coding

* `health_condition_detail` is raw text from `group` / `type` / `groups` / `disease_state` headers. Several usable sheets carry study-design labels rather than diagnoses (PRJEB36140 `Group` = pre-FMT / post-FMT / Donor; PRJNA1261967 `Groups` = D+R- / D+R+ / D-R-; PRJNA668607 `Type` = index case / contact_n). They are committed as raw detail per the task and must be coded (or discarded) by the health_condition vocabulary step; PRJNA686265 `Cohort` (= TZ) was excluded as ambiguous.
* The prefix-stripped join variant (confidence 0.8) produced no usable sheet once join tokens were required to contain a digit, be ≥ 3 characters and not be purely numeric — without that guard it produced two false joins (numeric `orf_start` and age-in-months columns matching stripped library-name suffixes), which are what the guard is for.
* Bare `Age` headers were read as years (adult rule); the resulting ages span 2.0–70.5 years, so child cohorts under bare `Age` are still committed in years.
* Sample IDs in most supplements are internal names (e.g. `D.01`, `VA36`) that match neither an accession nor the deposited sample_title / library_name; those sheets fail the exact-ID gate by design and are not rescued here (no fuzzy matching, no LLM).
* All 228 PMCIDs returned HTTP 200 from the Europe PMC supplementaryFiles endpoint in this run (no 500s); the endpoint was slow (~50 s per zip at 2 workers).

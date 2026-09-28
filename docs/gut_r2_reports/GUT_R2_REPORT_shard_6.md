# GUT R2 deterministic supplementary-table extraction — shard 6 of 8

Scope `gut_all` (config/packs/gut.yaml), route R2, determined_by `gut_r2_header_named`, src_track `gut_all_v1`, release R2026.7 / package 1.8.0. Method = catalog-pipeline `gapfill_samples` R2 (exact-ID gate ≥ 50 % rows or ≥ 20 hits; matrix sheets excluded; header-named columns only), plus a prefix-stripped join variant (confidence 0.8) tried only when the raw gate fails. No LLM calls were made (n_llm_calls = 0).

## Coverage

| metric | value |
|---|---|
| studies in shard | 164 |
| PMCIDs in shard | 237 |
| PMCIDs fetch attempted | 237 |
| fetch outcomes (per PMCID) | {"200": 191, "200_no_supp_files": 46} |
| PMCIDs whose zip held ≥ 1 readable table (xlsx/xls/csv/tsv/txt) | 92 |
| studies with ≥ 1 zip (HTTP 200 with a zip body) | 136 |
| studies with ≥ 1 zip containing readable tables | 73 |
| sheets gated | 1167 (exact gate passed: 86; usable = gate + non-matrix + header-named field column: 25, variants {"exact": 25}) |
| studies with ≥ 1 gate-passing usable sheet | 12 |
| studies with ≥ 1 committed row | 12 |
| determination rows (after dedupe + validators) | 5131 (validator-rejected: 0; by join variant {"exact": 5131}) |
| distinct samples covered | 2046 |
| conflicts between sheets (kept sheet with more exact hits) | 55 |

## Rows and samples per field

| field | rows | samples | studies |
|---|---|---|---|
| age_at_collection_days | 768 | 768 | 6 |
| bmi | 397 | 397 | 3 |
| country | 109 | 109 | 1 |
| health_condition_detail | 876 | 876 | 5 |
| sex | 1116 | 1116 | 8 |
| subject_id | 1066 | 1066 | 6 |
| timepoint_label | 799 | 799 | 3 |

## Per-study yield (rows)

| study | rows | samples | fields | PMCIDs |
|---|---|---|---|---|
| PRJEB28097 | 66 | 66 | subject_id | PMC9972980 |
| PRJEB32762 | 920 | 230 | age_at_collection_days, bmi, health_condition_detail, sex | PMC11974365 |
| PRJEB7774 | 327 | 109 | age_at_collection_days, bmi, country | PMC12539022 |
| PRJEB87602 | 780 | 260 | health_condition_detail, sex, subject_id | PMC10673813 |
| PRJNA1403442 | 39 | 13 | health_condition_detail, sex, timepoint_label | PMC13367979 |
| PRJNA309322 | 8 | 8 | sex | PMC4919841 |
| PRJNA484031 | 172 | 43 | age_at_collection_days, health_condition_detail, sex, subject_id | PMC7045296 |
| PRJNA675598 | 814 | 330 | age_at_collection_days, health_condition_detail, sex | PMC10726799 |
| PRJNA688274 | 760 | 380 | subject_id, timepoint_label | PMC8182900 |
| PRJNA872328 | 143 | 143 | subject_id | PMC10433802 |
| PRJNA890867 | 174 | 58 | age_at_collection_days, bmi, sex | PMC9767906 |
| PRJNA945408 | 928 | 406 | age_at_collection_days, sex, subject_id, timepoint_label | PMC10790752 |

## Header map (headers mapped to pack fields)

| header_norm | field | parser | n_sheets | n_sheets_gated | reason |
|---|---|---|---|---|---|
| age | age_at_collection_days | age_bare_years | 32 | 10 | infant_field_map + gut bare-age-years override |
| age_years | age_at_collection_days | age_numeric | 3 | 0 | infant_field_map |
| ageyr | age_at_collection_days | age_header_unit | 1 | 1 | age header with unit |
| age_yrs | age_at_collection_days | age_numeric | 1 | 1 | infant_field_map |
| age_in_months | age_at_collection_days | age_header_unit | 1 | 0 | age header with unit |
| antibiotic | antibiotic_exposure | categorical_yesno | 2 | 1 | infant_field_map |
| antibiotics | antibiotic_exposure | categorical_yesno | 1 | 0 | infant_field_map |
| bmi | bmi | bmi_numeric | 13 | 4 | bmi header list |
| bmi_kg_m2 | bmi | bmi_numeric | 1 | 0 | bmi header list |
| bmi_kg_m | bmi | bmi_numeric | 1 | 0 | bmi header list |
| country | country | country | 5 | 0 | infant_field_map |
| geographic_location_country_and_or_sea | country | country | 1 | 1 | infant_field_map |
| nationality | country | country | 1 | 0 | country header list |
| group | health_condition_detail | raw_text | 36 | 7 | disease/diagnosis/group header list |
| disease | health_condition_detail | raw_text | 9 | 1 | disease/diagnosis/group header list |
| disease_status | health_condition_detail | raw_text | 9 | 0 | disease/diagnosis/group header list |
| condition | health_condition_detail | raw_text | 4 | 0 | disease/diagnosis/group header list |
| diagnosis | health_condition_detail | raw_text | 2 | 0 | disease/diagnosis/group header list |
| cohort | health_condition_detail | raw_text | 2 | 0 | disease/diagnosis/group header list |
| phenotype | health_condition_detail | raw_text | 2 | 0 | disease/diagnosis/group header list |
| disease_type | health_condition_detail | raw_text | 1 | 0 | disease/diagnosis/group header list |
| subgroup | health_condition_detail | raw_text | 1 | 0 | disease/diagnosis/group header list |
| group_name | health_condition_detail | raw_text | 1 | 0 | disease/diagnosis/group header list |
| gender | sex | categorical_sex | 28 | 8 | infant_field_map |
| sex | sex | categorical_sex | 13 | 5 | infant_field_map |
| individual | subject_id | identifier | 9 | 0 | subject header list |
| subject_id | subject_id | identifier | 9 | 7 | infant_field_map |
| patient_id | subject_id | identifier | 5 | 3 | infant_field_map |
| patientid | subject_id | identifier | 3 | 1 | subject header list |
| patient_number | subject_id | identifier | 3 | 3 | subject header list |
| volunteer_number | subject_id | identifier | 2 | 1 | subject header list |
| patient | subject_id | identifier | 2 | 0 | infant_field_map |
| study_id | subject_id | identifier | 2 | 1 | subject header list |
| subject | subject_id | identifier | 2 | 1 | infant_field_map |
| participant_id | subject_id | identifier | 1 | 0 | infant_field_map |
| donor | subject_id | identifier | 1 | 0 | subject header list |
| pid | subject_id | identifier | 1 | 1 | subject header list |
| participant | subject_id | identifier | 1 | 0 | infant_field_map |
| subjectid | subject_id | identifier | 1 | 0 | infant_field_map |
| timepoint | timepoint_label | label | 27 | 9 | infant_field_map |
| day | timepoint_label | label | 4 | 0 | infant_field_map |
| visit | timepoint_label | label | 2 | 1 | infant_field_map |
| time_point | timepoint_label | label | 2 | 0 | infant_field_map |
| week | timepoint_label | label | 2 | 0 | infant_field_map |

## Top skipped headers (field-like but ambiguous or out of pack; gate-passing sheets first)

| header_norm | reason | n_sheets | n_sheets_gated |
|---|---|---|---|
| type | ambiguous bare header 'type' (skipped) | 19 | 3 |
| cohort_type_antibiotics_or_not | antibiotic-like header not yes/no (skipped) | 3 | 3 |
| state | ambiguous bare header 'state' (skipped) | 4 | 2 |
| timepoint_1 | timepoint-like header not in list (skipped) | 3 | 2 |
| subject_id_1 | subject-like header not an id (skipped) | 2 | 2 |
| subject_id_2 | subject-like header not an id (skipped) | 2 | 2 |
| samesubject | subject-like header not an id (skipped) | 2 | 2 |
| timepoint_2 | timepoint-like header not in list (skipped) | 2 | 2 |
| sametimepoint | timepoint-like header not in list (skipped) | 2 | 2 |
| patients_group | subject-like header not an id (skipped) | 2 | 2 |
| class | ambiguous bare header 'class' (skipped) | 58 | 1 |
| total_marker_coverage | age-like header not a collection age (skipped) | 5 | 1 |
| identified_phage_contigs | age-like header, pattern not recognised (skipped) | 2 | 1 |
| phage_species | age-like header, pattern not recognised (skipped) | 2 | 1 |
| metagenomeid | age-like header, pattern not recognised (skipped) | 1 | 1 |
| gi_sympt_anemia | disease-like header not in list (skipped) | 1 | 1 |
| gi_sympt_bleed | disease-like header not in list (skipped) | 1 | 1 |
| gi_sympt_diarrhea | disease-like header not in list (skipped) | 1 | 1 |
| gi_sympt_fever | disease-like header not in list (skipped) | 1 | 1 |
| gi_sympt_none | disease-like header not in list (skipped) | 1 | 1 |
| gi_sympt_weight | disease-like header not in list (skipped) | 1 | 1 |
| deploy_med_visitdat | timepoint-like header not in list (skipped) | 1 | 1 |
| disease_course | disease-like header not in list (skipped) | 1 | 1 |
| disease_duration | disease-like header not in list (skipped) | 1 | 1 |
| disease_course_control | disease-like header not in list (skipped) | 1 | 1 |
| human_gut_environmental_package | age-like header not a collection age (skipped) | 1 | 1 |
| age_range_in_years | age-like header not a collection age (skipped) | 1 | 1 |
| size_of_assembly_metagenome_size | age-like header, pattern not recognised (skipped) | 1 | 1 |
| average_contig_size | age-like header not a collection age (skipped) | 1 | 1 |
| age_at_colonoscopy_years | age-like header, pattern not recognised (skipped) | 1 | 1 |

## Cell values rejected by the parsers (header mapped, value not committable)

| field | parser | reason | n_cells | example |
|---|---|---|---|---|
| age_at_collection_days | age_bare_years | range/threshold not a value | 261 | 56-60 |
| age_at_collection_days | age_bare_years | unparsed | 182 | 100+ |

## Conflicts (55; see gut_r2_conflicts_shard_6.csv)

- PRJNA484031 health_condition_detail: RB (kept, paper.supp.Table_S7_Enterotype_information.xlsx[group!group]) vs R
- PRJNA484031 health_condition_detail: NRB (kept, paper.supp.Table_S7_Enterotype_information.xlsx[group!group]) vs NR
- PRJNA484031 health_condition_detail: NRB (kept, paper.supp.Table_S7_Enterotype_information.xlsx[group!group]) vs NR
- PRJNA484031 health_condition_detail: RB (kept, paper.supp.Table_S7_Enterotype_information.xlsx[group!group]) vs R
- PRJNA484031 health_condition_detail: RB (kept, paper.supp.Table_S7_Enterotype_information.xlsx[group!group]) vs R
- PRJNA484031 health_condition_detail: RB (kept, paper.supp.Table_S7_Enterotype_information.xlsx[group!group]) vs R
- PRJNA484031 health_condition_detail: NRB (kept, paper.supp.Table_S7_Enterotype_information.xlsx[group!group]) vs NR
- PRJNA484031 health_condition_detail: RB (kept, paper.supp.Table_S7_Enterotype_information.xlsx[group!group]) vs R
- PRJNA484031 health_condition_detail: NRB (kept, paper.supp.Table_S7_Enterotype_information.xlsx[group!group]) vs NR
- PRJNA484031 health_condition_detail: NRB (kept, paper.supp.Table_S7_Enterotype_information.xlsx[group!group]) vs NR

## Fetch failures / non-usable PMCIDs

46 PMCIDs without a usable zip: {"200_no_supp_files": 46}

## Method notes / limitations

- Deterministic only: header names are matched against the infant `attribute_field_map.csv` (pruned of infant-package couplings such as `isolate`, `age_group`, `babyid_dol`) plus the gut header lists in `gut_r2_shard.py`; bare `Age`/`host_age` headers are read as years unless an `age_unit(s)` column exists (parse_note records the assumption); age ranges/thresholds (`100+`, `20-30`) are never values.
- Side-by-side sub-tables in one sheet are segmented on all-empty separator columns; only the block holding the matched id column is read (this removed 80 spurious cross-block conflicts in PMC10726799 during development).
- Two-sheet joins (participant table ↔ sample table via participant id) are out of scope for this route; such sheets appear in the gate table as gate-passing but without header-named field columns, or vice versa.
- `health_condition_detail` is raw text (code assigned downstream); purely numeric coded groups are skipped. Bare `group`/`diagnosis`/`disease`/`cohort` headers are committed; bare `type`/`class`/`status`/`category`/`arm` are listed as ambiguous and skipped.
- Fetch: Europe PMC `supplementaryFiles?includeInlineImage=false` (the default endpoint took 50–70 s per zip); ≤ 2 concurrent; HTTP 429/5xx retried once with backoff; a 240 s / 400 MB cap per zip aborts trickle downloads (status ABORT).- `antibiotic_exposure`: 0 rows. The only antibiotic header in a gate-passing sheet (PRJNA945408 / PMC10790752, column `ANTIBIOTIC`) is a per-episode adverse-event checkbox with values `CHECKED` (4 cells), not a yes/no exposure — not committable by the yes/no parser; the cohort-level rifaximin/placebo `Randomisation` column is a trial arm, not an exposure, and was not mapped.
- `country`: the only committed values come from PRJEB7774 (header `Country`); `COUNTRY_NAME` in PRJNA945408 is the travel destination and was deliberately not mapped.
- Fetch used a bounded streaming fetcher (`fetch_rest.py`) for 160 of 237 PMCIDs after the pipeline's `HL.fetch` (no total-time cap) stalled on very large trickle downloads; the first 77 PMCIDs came through `harvest_lib` into `CATALOG_CACHE_DIR`. All 237 PMCIDs returned HTTP 200 (46 of them an errorBean "no supplementary files" body); no 429/5xx were met in this shard.

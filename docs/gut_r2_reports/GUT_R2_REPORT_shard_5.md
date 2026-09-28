# GUT R2 deterministic supplementary-table extraction — shard 5

Scope: gut_all (src_track gut_all_v1, release R2026.7, package 1.8.0). Route R2, header-named columns only, no LLM calls. All 221 PMCIDs fetched and processed (full coverage of the shard).

## Coverage

- studies in shard: 164; PMCIDs linked: 221; PMCIDs processed (fetch attempted): 221
- fetch outcomes: zip_ok=189, no_supplementary_zip=32
- studies with ≥ 1 supplementary zip: 145
- studies with ≥ 1 sheet passing the exact-ID gate (either variant): 26
- studies with ≥ 1 r2-usable sheet (gate + non-matrix + ≥ 1 header-named pack column): 15
- sheets gated: 1337; gate-passing: 84; usable: 25; prefix-stripped variant usable: 2
- determination rows: 6817; samples covered (any field): 3088 of 23549 BioSamples in the shard
- conflicts: 280 (cross_sheet=280)

## Rows and samples per field

| field | rows | samples | studies |
|---|---|---|---|
| age_at_collection_days | 2040 | 2040 | 11 |
| sex | 1847 | 1847 | 9 |
| bmi | 431 | 431 | 3 |
| country | 55 | 55 | 1 |
| health_condition_detail | 827 | 827 | 5 |
| antibiotic_exposure | 0 | 0 | 0 |
| subject_id | 858 | 858 | 5 |
| timepoint_label | 759 | 759 | 5 |

## Studies with usable sheets

| study | pmcid | file | sheet | join column | variant | join hits | fields |
|---|---|---|---|---|---|---|---|
| PRJDB4176 | PMC13553305 | 41588_2026_2692_MOESM4_ESM.xlsx | Supplementary _Table_2 | Metagenome ID | prefix_stripped | 146.0 | age_at_collection_days,bmi,health_condition_detail,sex |
| PRJDB4176 | PMC13553305 | 41588_2026_2692_MOESM4_ESM.xlsx | Supplementary _Table_1 | Metagenome ID | prefix_stripped | 51.0 | age_at_collection_days,bmi,sex |
| PRJEB20800 | PMC7338343 | Data Sheet 2.XLSX | Sheet1 | SAMPLE ID | exact | 29.0 | subject_id,timepoint_label |
| PRJEB49124 | PMC11377447 | 41467_2024_52097_MOESM4_ESM.xlsx | Metadata | Subject ID | exact | 234.0 | age_at_collection_days,sex |
| PRJEB49124 | PMC11377447 | 41467_2024_52097_MOESM5_ESM.xlsx | Species Abundances | Subject ID | exact | 213.0 |  |
| PRJEB49124 | PMC11377447 | 41467_2024_52097_MOESM5_ESM.xlsx | Genus Abundances | Subject ID | exact | 213.0 |  |
| PRJNA1265906 | PMC13045140 | 40168_2026_2344_MOESM2_ESM.xlsx | Supplementary Table 5 ped | type_id | exact | 134.0 | age_at_collection_days |
| PRJNA289586 | PMC6424576 | elife-42693-supp1.xlsx | Sheet1 | BioSample_accession | exact | 176.0 | age_at_collection_days,bmi,health_condition_detail,sex,subject_id,timepoint_label |
| PRJNA289586 | PMC12440900 | Table1.xlsx | 样本信息 | Run | exact | 85.0 | age_at_collection_days,bmi,sex |
| PRJNA391226 | PMC6043814 | Table_1.XLSX | Table S1 | Sample | exact | 61.0 | age_at_collection_days,bmi |
| PRJNA521455 | PMC7118151 | 42003_2020_859_MOESM3_ESM.xlsx | sample _metadata | Sample.ID | exact | 114.0 | age_at_collection_days,sex |
| PRJNA544527 | PMC10127601 | mbio.02502-22-s0006.xlsx | sampling_metadata | run_accession | exact | 365.0 | subject_id |
| PRJNA624223 | PMC8653907 | Table_1.xlsx | Sheet1 | Id | exact | 36.0 | age_at_collection_days,health_condition_detail,sex |
| PRJNA675301 | PMC11060737 | jci-134-174726-s046.xlsx | Supplemental Figure 2B | SampleID | exact | 414.0 | health_condition_detail,timepoint_label |
| PRJNA737472 | PMC12047655 | sample.tsv |  | biosample | exact | 224.0 | subject_id |
| PRJNA737472 | PMC12047655 | 2024-02-29_existing_biosamples.tsv |  | Accession | exact | 169.0 |  |
| PRJNA737472 | PMC12047655 | 2024-03-01_biosample_upload3.tsv |  | sample_id | exact | 55.0 | age_at_collection_days,country,health_condition_detail,sex |
| PRJNA737472 | PMC12047655 | visit.tsv |  | donor_sample_id | exact | 42.0 | timepoint_label |
| PRJNA737472 | PMC8976058 | 41598_2022_9307_MOESM2_ESM.xlsx | Table S3 | baseline | exact | 16.0 |  |
| PRJNA737472 | PMC8976058 | 41598_2022_9307_MOESM2_ESM.xlsx | Table S5 | pre_maintenance_4 | exact | 13.0 |  |
| PRJNA737472 | PMC8976058 | 41598_2022_9307_MOESM2_ESM.xlsx | Table S6 | baseline | exact | 12.0 |  |
| PRJNA806955 | PMC8966894 | Table_1.xls | Tab S1 metadata | Samples | exact | 19.0 | age_at_collection_days,sex |
| PRJNA850529 | PMC10134842 | msystems.00986-22-s0001.xlsx | Sheet1 | code | exact | 922.0 | age_at_collection_days,sex |
| PRJNA905672 | PMC10527824 | supplementary data S1.xlsx | samples characterisation | code sample | exact | 64.0 | subject_id |
| PRJNA972625 | PMC11861499 | 262_2024_3918_MOESM1_ESM.xlsx | S1_Table | Id | exact | 98.0 | age_at_collection_days,sex,timepoint_label |

## Header map (mapped headers seen in gate-passing sheets)

| header_norm | field | parser | unit | gate-passing sheets | value-level skip |
|---|---|---|---|---|---|
| age | age_at_collection_days | age_numeric_or_text | years | 9 |  |
| sex | sex | categorical_sex |  | 8 |  |
| subject_id | subject_id | identifier |  | 8 |  |
| group | health_condition_detail | raw_text |  | 4 | secondary column for health_condition_detail in the same sheet (kept 'host_disease') |
| bmi | bmi | bmi_numeric |  | 2 |  |
| time | timepoint_label | label |  | 2 |  |
| gender | sex | categorical_sex |  | 2 |  |
| host | subject_id | identifier |  | 2 | secondary column for subject_id in the same sheet (kept 'host_subject_id') |
| host_disease | health_condition_detail | raw_text |  | 2 |  |
| body_mass_index | bmi | bmi_numeric |  | 2 |  |
| subject | subject_id | identifier |  | 1 |  |
| timepoint | timepoint_label | label |  | 1 |  |
| cohort | health_condition_detail | raw_text |  | 1 | secondary column for health_condition_detail in the same sheet (kept 'group') |
| patient_id | subject_id | identifier |  | 1 |  |
| study_day | timepoint_label | label |  | 1 |  |
| study_group | health_condition_detail | raw_text |  | 1 |  |
| age_years | age_at_collection_days | age_numeric_or_text | years | 1 |  |
| status | health_condition_detail | raw_text |  | 1 | status/group column holds administrative or boolean values, not conditions |
| visit_id | timepoint_label | label |  | 1 |  |
| antibiotics | antibiotic_exposure | categorical_yesno |  | 1 | antibiotic column not yes/no coded |
| bmi_kg_m2 | bmi | bmi_numeric |  | 1 |  |
| code_patient | subject_id | identifier |  | 1 |  |
| host_age | age_at_collection_days | age_numeric_or_text | years | 1 |  |
| host_sex | sex | categorical_sex |  | 1 |  |
| host_subject_id | subject_id | identifier |  | 1 |  |
| age_in_years | age_at_collection_days | age_numeric_or_text | years | 1 |  |
| age_visit | age_at_collection_days | age_numeric_or_text | years | 1 |  |
| antibiotic_use | antibiotic_exposure | categorical_yesno |  | 1 | antibiotic column not yes/no coded |
| geo_loc_name | country | country |  | 1 |  |

## Top skipped headers in usable sheets (not mapped to a pack field)

- `sample_id` × 4 sheets — not a pack field header
- `baseline` × 3 sheets — not a pack field header
- `collection_date` × 3 sheets — not a pack field header
- `followup_1` × 3 sheets — not a pack field header
- `followup_2` × 3 sheets — not a pack field header
- `followup_3` × 3 sheets — not a pack field header
- `post_antibiotic` × 3 sheets — not a pack field header
- `pre_maintenance_1` × 3 sheets — not a pack field header
- `pre_maintenance_2` × 3 sheets — not a pack field header
- `pre_maintenance_3` × 3 sheets — not a pack field header
- `pre_maintenance_4` × 3 sheets — not a pack field header
- `pre_maintenance_5` × 3 sheets — not a pack field header
- `pre_maintenance_6` × 3 sheets — not a pack field header
- `alcohol` × 2 sheets — not a pack field header
- `brinkman_index` × 2 sheets — not a pack field header
- `metagenome_id` × 2 sheets — not a pack field header
- `sample` × 2 sheets — not a pack field header
- `sample_type` × 2 sheets — not a pack field header
- `ve_stool_qpcr` × 2 sheets — not a pack field header
- `ve_throat_swab` × 2 sheets — not a pack field header
- `accession` × 1 sheets — not a pack field header
- `adjuvant_cx` × 1 sheets — not a pack field header
- `age_category` × 1 sheets — age header without a recognisable unit
- `amoxycillin` × 1 sheets — not a pack field header
- `antiretroviral_drug_combinations` × 1 sheets — not a pack field header
- `art_duration_year` × 1 sheets — not a pack field header
- `average` × 1 sheets — not a pack field header
- `b_cells_perc_byhuman` × 1 sheets — not a pack field header
- `bases` × 1 sheets — not a pack field header
- `bio` × 1 sheets — not a pack field header
- `bioproject` × 1 sheets — not a pack field header
- `bioproject_accession` × 1 sheets — not a pack field header
- `biosample` × 1 sheets — not a pack field header
- `biosample_accession` × 1 sheets — not a pack field header
- `biosample_name` × 1 sheets — not a pack field header
- `biosample_organism_name` × 1 sheets — not a pack field header
- `body_site` × 1 sheets — not a pack field header
- `cd16_cd56_nk_cell_counts_cells_mm3` × 1 sheets — not a pack field header
- `cd16_cd56_nk_cell_ratio` × 1 sheets — not a pack field header
- `cd19_b_cell_counts_cells_mm3` × 1 sheets — not a pack field header

## Columns skipped at value level

- `Antibiotic use` → antibiotic_exposure: antibiotic column not yes/no coded (1 sheets)
- `Group` → health_condition_detail: secondary column for health_condition_detail in the same sheet (kept 'host_disease') (1 sheets)
- `Status` → health_condition_detail: status/group column holds administrative or boolean values, not conditions (1 sheets)
- `antibiotics` → antibiotic_exposure: antibiotic column not yes/no coded (1 sheets)
- `cohort` → health_condition_detail: secondary column for health_condition_detail in the same sheet (kept 'group') (1 sheets)
- `host` → subject_id: secondary column for subject_id in the same sheet (kept 'host_subject_id') (1 sheets)

## Conflicts (first 30)

- cross_sheet PRJNA289586 SAMN09837370 age_at_collection_days: 22646|25202 → kept PMC6424576|elife-42693-supp1.xlsx|Sheet1 (176 hits)
- cross_sheet PRJNA289586 SAMN09837370 bmi: 25.2|29.94 → kept PMC6424576|elife-42693-supp1.xlsx|Sheet1 (176 hits)
- cross_sheet PRJNA289586 SAMN09837370 sex: female|male → kept PMC6424576|elife-42693-supp1.xlsx|Sheet1 (176 hits)
- cross_sheet PRJNA289586 SAMN09837371 age_at_collection_days: 22646|25202 → kept PMC6424576|elife-42693-supp1.xlsx|Sheet1 (176 hits)
- cross_sheet PRJNA289586 SAMN09837371 bmi: 27.0|29.45 → kept PMC6424576|elife-42693-supp1.xlsx|Sheet1 (176 hits)
- cross_sheet PRJNA289586 SAMN09837371 sex: female|male → kept PMC6424576|elife-42693-supp1.xlsx|Sheet1 (176 hits)
- cross_sheet PRJNA289586 SAMN09837372 age_at_collection_days: 13514|22646 → kept PMC6424576|elife-42693-supp1.xlsx|Sheet1 (176 hits)
- cross_sheet PRJNA289586 SAMN09837372 health_condition_detail: diabetes_type1|type 1 diabetes mellitus → kept PMC6424576|elife-42693-supp1.xlsx|Sheet1 (176 hits)
- cross_sheet PRJNA289586 SAMN09837372 sex: female|male → kept PMC6424576|elife-42693-supp1.xlsx|Sheet1 (176 hits)
- cross_sheet PRJNA289586 SAMN09837373 bmi: 16.93|26.39 → kept PMC6424576|elife-42693-supp1.xlsx|Sheet1 (176 hits)
- cross_sheet PRJNA289586 SAMN09837374 bmi: 17.03|26.24 → kept PMC6424576|elife-42693-supp1.xlsx|Sheet1 (176 hits)
- cross_sheet PRJNA289586 SAMN09837375 age_at_collection_days: 21915|5114 → kept PMC6424576|elife-42693-supp1.xlsx|Sheet1 (176 hits)
- cross_sheet PRJNA289586 SAMN09837376 age_at_collection_days: 1096|20819 → kept PMC6424576|elife-42693-supp1.xlsx|Sheet1 (176 hits)
- cross_sheet PRJNA289586 SAMN09837376 bmi: 17.18|37.12 → kept PMC6424576|elife-42693-supp1.xlsx|Sheet1 (176 hits)
- cross_sheet PRJNA289586 SAMN09837376 health_condition_detail: control|type 1 diabetes mellitus → kept PMC6424576|elife-42693-supp1.xlsx|Sheet1 (176 hits)
- cross_sheet PRJNA289586 SAMN09837376 sex: female|male → kept PMC6424576|elife-42693-supp1.xlsx|Sheet1 (176 hits)
- cross_sheet PRJNA289586 SAMN09837377 age_at_collection_days: 1826|20819 → kept PMC6424576|elife-42693-supp1.xlsx|Sheet1 (176 hits)
- cross_sheet PRJNA289586 SAMN09837377 bmi: 14.96|37.21 → kept PMC6424576|elife-42693-supp1.xlsx|Sheet1 (176 hits)
- cross_sheet PRJNA289586 SAMN09837377 sex: female|male → kept PMC6424576|elife-42693-supp1.xlsx|Sheet1 (176 hits)
- cross_sheet PRJNA289586 SAMN09837378 age_at_collection_days: 1826|20819 → kept PMC6424576|elife-42693-supp1.xlsx|Sheet1 (176 hits)
- cross_sheet PRJNA289586 SAMN09837378 bmi: 15.4|36.99 → kept PMC6424576|elife-42693-supp1.xlsx|Sheet1 (176 hits)
- cross_sheet PRJNA289586 SAMN09837378 sex: female|male → kept PMC6424576|elife-42693-supp1.xlsx|Sheet1 (176 hits)
- cross_sheet PRJNA289586 SAMN09837379 age_at_collection_days: 13149|13514 → kept PMC6424576|elife-42693-supp1.xlsx|Sheet1 (176 hits)
- cross_sheet PRJNA289586 SAMN09837379 bmi: 31.51|36.33 → kept PMC6424576|elife-42693-supp1.xlsx|Sheet1 (176 hits)
- cross_sheet PRJNA289586 SAMN09837380 age_at_collection_days: 13149|13514 → kept PMC6424576|elife-42693-supp1.xlsx|Sheet1 (176 hits)
- cross_sheet PRJNA289586 SAMN09837380 bmi: 31.83|37.11 → kept PMC6424576|elife-42693-supp1.xlsx|Sheet1 (176 hits)
- cross_sheet PRJNA289586 SAMN09837381 age_at_collection_days: 13149|21184 → kept PMC6424576|elife-42693-supp1.xlsx|Sheet1 (176 hits)
- cross_sheet PRJNA289586 SAMN09837381 bmi: 23.17|31.72 → kept PMC6424576|elife-42693-supp1.xlsx|Sheet1 (176 hits)
- cross_sheet PRJNA289586 SAMN09837381 sex: female|male → kept PMC6424576|elife-42693-supp1.xlsx|Sheet1 (176 hits)
- cross_sheet PRJNA289586 SAMN09837382 age_at_collection_days: 14610|21184 → kept PMC6424576|elife-42693-supp1.xlsx|Sheet1 (176 hits)

## Observations for downstream adjudication

- PRJNA289586 has two linked papers (PMC6424576 eLife own-data, 176 exact hits; PMC12440900, 85 hits) whose per-sample age/BMI/sex disagree for 37–78 samples; the more-hits sheet was kept per rule — the PMC12440900 sheet looks unreliable and the retained values should still be checked.
- PRJNA737472: visit.tsv (recipient subject ids joined via donor_sample_id) conflicted with sample.tsv subject ids for 42 samples; sample.tsv kept.
- PRJNA521455 (Age_years 1.1–5.8 y) holds 31 samples aged ≤ 3 y and PRJNA1265906 (pediatric, bare 'age_visit' header, years assumed) holds ages 0–19 y — incidental infant-range samples inside non-infant studies; age rows carry 'bare age header, years assumed' in parse_note where the unit was not in the header.
- health_condition_detail raw text from 'group'/'cohort' headers includes non-disease strata (e.g. Omnivore / Vegan / EEN, COVID-19 case / Pneumonia control); code assignment is downstream.
- Antibiotic columns met (2) were coded as time-since-use or free text ('None' / 'yes' / date ranges), not yes/no, and were skipped; per-drug boolean columns (PMC11237811) were not read.
- Word (.docx) supplementary tables are not parsed (only xlsx/xls/csv/tsv/txt, incl. nested zips); n_docx per pmcid is in the log.
- Concurrency note: see gut_r2_log_shard_5.json notes (a duplicate fetch launcher ran ~10 min; otherwise ≤ 2 concurrent).
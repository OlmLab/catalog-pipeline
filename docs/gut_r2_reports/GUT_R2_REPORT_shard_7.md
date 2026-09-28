# GUT R2 deterministic supplementary-table extraction — shard 7 of 8

Generated 2026-09-28T04:34:57Z (UTC). Method: pipeline R2 rules (exact-ID gate ≥ 50 % of rows or ≥ 20 exact hits on BioSample / run / experiment / library_name / sample_title; matrix sheets excluded; header-named columns only; no LLM calls).


## Method notes and deviations

* Code: `gut_r2_shard.py` re-implements `gapfill_samples.r2_gate` / `r2_extract` locally (imports `_supp_id_columns`, `norm_key`, `q12`, `DET_COLS` from the pipeline and the `r1_parsers` age/sex/yes-no/country parsers). Paper links come from the shard's pmcids input instead of a package `study_paper_links.csv`. Fetch via `harvest_lib.fetch` (Europe PMC supplementaryFiles, 2 workers, max_retries=3, cache under `./r2cache`). No LLM calls were made.
* **Extension of the exact-ID universe:** the ENA `sample_alias` (BioSample name) of each run was added to the join keys (fetched from the ENA portal for the 164 studies; present for 25,778 of 25,935 runs). Without it the gate passed for 1 study on the first 18 zips; supplementary tables key on the BioSample name far more often than on the ENA `sample_title` (which is generic for 76 % of runs here). Rows joined on `sample_alias` carry `parse_note` "… join on <column>" like every other exact join and confidence 0.85.
* Join tokens shorter than 3 characters, and tokens shared by more than one BioSample of the study, never count as exact hits (guards against generic titles such as 'Human Gut' or '1').
* Bare `Age` headers were read as years only when the column's numeric values have median ≥ 18 and max ≤ 120 (adult distribution); otherwise the header is listed as ambiguous and skipped. No bare-Age column in this shard fell in the ambiguous branch.
* `health_condition_detail` is committed as raw group/status/cohort text (spec); values such as 'DA|DB', 'Y|K|C|S' or 'Gorilla|Human' (PRJNA635116 — a mixed-host deposit) are group codes for the downstream vocabulary step and are flagged above.
* Conflicts: the 2,081 between-sheet conflicts all come from PRJEB110772, where two 'Group' columns (frailty class vs Charlson index) have identical hit counts; the first-listed sheet (Source Data Fig. 2a, frailty) was kept per the more-hits rule with a tie. Intra-sheet conflicts (21) are multiple rows per sample with differing values — dropped, not committed.
* Zips larger than 80 MB per member file were skipped (none in this shard); Europe PMC returned 'not open access' error beans (HTTP 200, no zip) for 19 of 234 PMCIDs — recorded in `gut_r2_log_shard_7.json`.

## Coverage

| metric | value |
|---|---|
| studies in shard | 164 |
| PMCIDs in shard | 234 |
| PMCIDs HTTP 200 | 234 |
| PMCIDs returning a real zip | 215 |
| PMCIDs answered 'not open access' (Europe PMC error bean, no zip) | 19 |
| studies with all PMCIDs fetched | 164 |
| studies with ≥ 1 supplementary zip | 154 |
| studies with ≥ 1 tabular sheet | 86 |
| studies with ≥ 1 gate-passing sheet | 26 |
| studies with ≥ 1 r2-usable sheet (gate + non-matrix + header-named field column) | 18 |
| studies with ≥ 1 determination row | 16 |
| sheets read / gate-passing / matrix / usable | 1150 / 81 / 25 / 26 |
| gate variants among passing sheets | {'raw': 80, 'prefix_stripped': 1} |
| determination rows | 4485 |
| distinct samples with ≥ 1 row | 3498 |
| conflicts logged (between sheets / intra-sheet) | 2081 / 21 |

## Rows and samples per field

| field | rows | samples |
|---|---|---|
| age_at_collection_days | 335 | 335 |
| bmi | 45 | 45 |
| health_condition_detail | 2730 | 2730 |
| sex | 503 | 503 |
| subject_id | 813 | 813 |
| timepoint_label | 59 | 59 |

## Confidence

0.85: 4481 rows, 0.8: 4 rows (0.85 = raw exact-ID join; 0.8 = prefix-stripped sample_title / library_name join variant).

## Header map (mapped headers, top by sheet count)

| header_norm | field | parser | unit | n_sheets |
|---|---|---|---|---|
| age | age_at_collection_days | age_numeric | years | 5 |
| age_years | age_at_collection_days | age_numeric | years | 1 |
| antibiotic_therapy | antibiotic_exposure | categorical_yesno |  | 1 |
| bmi | bmi | numeric_bmi |  | 2 |
| body_mass_index | bmi | numeric_bmi |  | 1 |
| group | health_condition_detail | text |  | 12 |
| health | health_condition_detail | text |  | 1 |
| cohort | health_condition_detail | text |  | 1 |
| disease_state | health_condition_detail | text |  | 1 |
| status | health_condition_detail | text |  | 1 |
| gender | sex | categorical_sex |  | 5 |
| sex | sex | categorical_sex |  | 5 |
| subject_id | subject_id | identifier |  | 3 |
| patient_id | subject_id | identifier |  | 3 |
| subject | subject_id | identifier |  | 1 |
| patientid | subject_id | identifier |  | 1 |
| time_point | timepoint_label | label |  | 1 |
| days | timepoint_label | label |  | 1 |
| time | timepoint_label | label |  | 1 |

## Top skipped headers (gate-passing metadata-shaped sheets, ≤ 60 columns)

| header_norm | n_sheets | reason |
|---|---|---|
| sample_id | 13 | ambiguous/range or non-target header (listed) |
| sample_name | 7 | ambiguous/range or non-target header (listed) |
| sample | 7 | ambiguous/range or non-target header (listed) |
| nan_2 | 6 | not a pack field header |
| nan_3 | 4 | not a pack field header |
| sra_accession | 4 | not a pack field header |
| sample_type | 4 | ambiguous/range or non-target header (listed) |
| patient_1004_lgg_week_4 | 3 | not a pack field header |
| patient_1069_placebo_baseline | 3 | not a pack field header |
| patient_1068_placebo_baseline | 3 | not a pack field header |
| patient_1077_lgg_baseline | 3 | not a pack field header |
| patient_1001_placebo_week_4 | 3 | not a pack field header |
| patient_1008_placebo_week_4 | 3 | not a pack field header |
| patient_1005_lgg_week_4 | 3 | not a pack field header |
| patient_1007_placebo_week_4 | 3 | not a pack field header |
| patient_1076_placebo_baseline | 3 | not a pack field header |
| patient_1009_placebo_week_4 | 3 | not a pack field header |
| patient_1075_placebo_baseline | 3 | not a pack field header |
| patient_1188_placebo_baseline | 3 | not a pack field header |
| patient_1078_lgg_baseline | 3 | not a pack field header |
| patient_1183_lgg_baseline | 3 | not a pack field header |
| patient_1186_lgg_baseline | 3 | not a pack field header |
| patient_1198_lgg_week_4 | 3 | not a pack field header |
| patient_1189_placebo_baseline | 3 | not a pack field header |
| patient_1190_lgg_baseline | 3 | not a pack field header |
| patient_1197_lgg_baseline | 3 | not a pack field header |
| patient_1199_placebo_baseline | 3 | not a pack field header |
| patient_1198_lgg_baseline | 3 | not a pack field header |
| patient_1009_placebo_baseline | 3 | not a pack field header |
| patient_1008_placebo_baseline | 3 | not a pack field header |
| patient_1199_placebo_week_4 | 3 | not a pack field header |
| patient_1183_lgg_week_4 | 3 | not a pack field header |
| patient_1189_placebo_week_4 | 3 | not a pack field header |
| patient_1005_lgg_week_24 | 3 | not a pack field header |
| patient_1197_lgg_week_24 | 3 | not a pack field header |
| patient_1069_placebo_week_24 | 3 | not a pack field header |
| patient_1078_lgg_week_24 | 3 | not a pack field header |
| patient_1183_lgg_week_24 | 3 | not a pack field header |
| patient_1186_lgg_week_24 | 3 | not a pack field header |
| patient_1188_placebo_week_24 | 3 | not a pack field header |
| patient_1189_placebo_week_24 | 3 | not a pack field header |
| patient_1190_lgg_week_24 | 3 | not a pack field header |
| patient_1198_lgg_week_24 | 3 | not a pack field header |
| patient_1199_placebo_week_24 | 3 | not a pack field header |
| patient_1004_lgg_week_24 | 3 | not a pack field header |
| patient_1188_placebo_week_4 | 3 | not a pack field header |
| patient_1001_placebo_week_24 | 3 | not a pack field header |
| patient_1077_lgg_week_4 | 3 | not a pack field header |
| patient_1195_lgg_week_4 | 3 | not a pack field header |
| patient_1068_placebo_week_4 | 3 | not a pack field header |
| patient_1069_placebo_week_4 | 3 | not a pack field header |
| patient_1075_placebo_week_4 | 3 | not a pack field header |
| patient_1076_placebo_week_4 | 3 | not a pack field header |
| patient_1078_lgg_week_4 | 3 | not a pack field header |
| patient_1005_lgg_baseline | 3 | not a pack field header |
| patient_1186_lgg_week_4 | 3 | not a pack field header |
| patient_1007_placebo_baseline | 3 | not a pack field header |
| patient_1195_lgg_baseline | 3 | not a pack field header |
| patient_1004_lgg_baseline | 3 | not a pack field header |
| hd_5 | 3 | not a pack field header |

Ambiguous headers deliberately skipped (listed for the curator): 9 distinct — sample_id, sample_name, sample, sample_type, id, nation, age, ethnicity, study

## Conflicts

| study_accession   | field_name              | kind           |    n |
|:------------------|:------------------------|:---------------|-----:|
| PRJEB110772       | health_condition_detail | between_sheets | 2081 |
| PRJEB8347         | timepoint_label         | intra_sheet    |   17 |
| PRJNA788972       | age_at_collection_days  | intra_sheet    |    2 |
| PRJNA788972       | bmi                     | intra_sheet    |    2 |

## Gate-failing studies with a near-miss ID column (diagnostic only; no rows committed)

Best column overlap under case-insensitive / cell-in-id / id-in-cell matching; a future 'suffix-stripped cell' or 'alias-with-suffix' join variant would be needed. See gut_r2_gate_nearmiss_shard_7.csv.

| study_accession   |   n_samples | example_alias                 | pmcid       | file                             | sheet                      | column              | example_cells                                                                    |   frac_case_insensitive |   frac_cell_in_id |   frac_id_in_cell |
|:------------------|------------:|:------------------------------|:------------|:---------------------------------|:---------------------------|:--------------------|:---------------------------------------------------------------------------------|------------------------:|------------------:|------------------:|
| PRJNA629755       |         154 | s.689438                      | PMC11264914 | msystems.00515-24-s0001.csv      | nan                        | fragments_total     | 1721|1721|1721                                                                   |                    0    |              1    |               0   |
| PRJNA547591       |         180 | CM.376_WGS                    | PMC7249393  | 13059_2020_2020_MOESM2_ESM.xlsx  | S18                        | Samples             | CM.7|CM.13|CM.16                                                                 |                    0    |              1    |               0   |
| PRJEB14155        |         172 | DBH1W00202                    | PMC10435514 | 41467_2023_40552_MOESM4_ESM.xlsx | Supplementary Data 1       | sseqid              | DBH1W00101_24276|DBH2U00901_106555|DBH2W01701_29102                              |                    0    |              0    |               1   |
| PRJNA1247491      |          90 | AGM9-AVG-A                    | PMC12307401 | Table_2.xlsx                     | Table S1                   | Samples             | M1-CTRL-A|M1-CTRL-B|M1-CTRL-C                                                    |                    0    |              1    |               0   |
| PRJEB88618        |           3 | Human Gut                     | PMC13087279 | 41467_2026_69760_MOESM3_ESM.xlsx | Figure 1a                  | Dataset             | Human Gut|Human Gut|Human Gut                                                    |                    0.67 |              0.67 |               1   |
| PRJNA749138       |           1 | Fecal sample                  | PMC10110541 | 41467_2023_37975_MOESM3_ESM.xlsx | Supplementary Data 1       | ARG#                | ARG004|ARG010|ARG011                                                             |                    0    |              1    |               0   |
| PRJEB53209        |          17 | GF11                          | PMC12911420 | msystems.01443-25-s0002.xlsx     | Table15                    | gene                | ERR9808324.13_k141_34865_8|ERR9808324.13_k141_34869_1|ERR9808324.17_k141_257818_ |                    0    |              0    |               1   |
| PRJEB42384        |          73 | ROMI_A04_15_PostART_w24_w24_3 | PMC9004083  | 40168_2022_1247_MOESM3_ESM.xlsx  | Additional Dataset S1      | Timepoint           | MVA1|MVA1|MVA1                                                                   |                    0    |              1    |               0   |
| PRJNA758252       |        1271 | SMB235082                     | PMC10551180 | DataSheet_2.xlsx                 | S_Tab1_Genera_Bone_ALL_FHS | N                   | 1227|1227|1227                                                                   |                    0    |              1    |               0   |
| PRJEB32731        |        1004 | 289362                        | PMC10115644 | 41591_2023_2248_MOESM3_ESM.xlsx  | Arivale_Metabolomics       | N                   | 1228|1229|1216                                                                   |                    0    |              1    |               0   |
| PRJEB64861        |         706 | Gut_100_Pre                   | PMC10477304 | 41467_2023_41042_MOESM4_ESM.xlsx | oral pathways MED diet     | s                   | 1032|1041|1056                                                                   |                    0    |              0.95 |               0   |
| PRJNA793776       |         130 | NC_59                         | PMC10173549 | 12916_2023_2878_MOESM2_ESM.xlsx  | Table S11                  | nsnps               | 2161|3693|3774                                                                   |                    0    |              0.67 |               0   |
| PRJEB50699        |          31 | MTG232                        | PMC12507277 | pcbi.1013470.s007.txt            | nan                        | >ERR8477561.4609978 | GGCAAGAGCACTCGGACTTCTGGATCTGGGGCTGGACCGTGATGTTACAGACTTAAGCGGGGGACAGAGAACGAAAGTCC |                    0    |              0    |               0.5 |

## Curator flags on committed raw-text values

health_condition_detail is committed as raw group/status text; the vocabulary code is assigned downstream. Distinct values per source column:

| study_accession   | evidence_source                                                          | value_normalized                                        |
|:------------------|:-------------------------------------------------------------------------|:--------------------------------------------------------|
| PRJEB110772       | paper.supp.41467_2026_75176_MOESM6_ESM.xlsx[Source Data Fig. 2a!Group]   | Mild frailty|Moderate frailty|No frailty|Severe frailty |
| PRJNA1307628      | paper.supp.41564_2025_2223_MOESM4_ESM.xlsx[metadata table!disease_state] | Ctrl:HC                                                 |
| PRJNA400628       | paper.supp.41467_2024_53829_MOESM3_ESM.xlsx[Sheet1!cohort]               | healthy|non-recurrer|recurrer                           |
| PRJNA401385       | paper.supp.Data_Sheet_1.xlsx[Table S1!Health]                            | Health|Patient|Test-P                                   |
| PRJNA530971       | paper.supp.Table_1.XLSX[Table S1!Group]                                  | PCOS patient|healthy control                            |
| PRJNA553191       | paper.supp.mSystems.00124-20-st001.xlsx[Supplementary Table 1!Group]     | C|K|S|Y                                                 |
| PRJNA635116       | paper.supp.mSystems.00815-20-sd001.xlsx[tab1!Group]                      | Gorilla|Human                                           |
| PRJNA701961       | paper.supp.13059_2023_2924_MOESM1_ESM.xlsx[a) Donor samples!Group]       | DA|DB                                                   |
| PRJNA701961       | paper.supp.13059_2023_2924_MOESM1_ESM.xlsx[b) Recipient samples!Group]   | DA|DB                                                   |
| PRJNA788972       | paper.supp.spectrum00925-21_supp_2_seq7.xlsx[Questionnaire!Group]        | After Voyage|Before Voyage                              |

## Per-study outcome

| study        |   pmcids |   fetched |   not_fetched |   sheets |   gate_pass |   usable |   rows |   samples | fields                                                |
|:-------------|---------:|----------:|--------------:|---------:|------------:|---------:|-------:|----------:|:------------------------------------------------------|
| PRJNA530971  |        3 |         3 |             0 |        9 |           1 |        1 |     92 |        92 | health_condition_detail                               |
| PRJNA407341  |        1 |         1 |             0 |        5 |           1 |        1 |    216 |        77 | age_at_collection_days;sex;subject_id                 |
| PRJNA401385  |        1 |         1 |             0 |       10 |           8 |        1 |     76 |        76 | health_condition_detail                               |
| PRJNA701961  |        1 |         1 |             0 |       30 |          12 |        3 |    109 |       109 | health_condition_detail                               |
| PRJNA400628  |        4 |         4 |             0 |       22 |           3 |        2 |    388 |       193 | health_condition_detail;subject_id;timepoint_label    |
| PRJNA707487  |        1 |         1 |             0 |       12 |           3 |        1 |    320 |       320 | subject_id                                            |
| PRJNA553191  |        4 |         4 |             0 |        7 |           1 |        1 |    168 |        56 | age_at_collection_days;health_condition_detail;sex    |
| PRJNA1307628 |        1 |         1 |             0 |       31 |           3 |        1 |    146 |        73 | health_condition_detail;subject_id                    |
| PRJNA788972  |        1 |         1 |             0 |        1 |           1 |        1 |      4 |         2 | health_condition_detail;sex                           |
| PRJEB110772  |        1 |         1 |             0 |       29 |           3 |        2 |   2081 |      2081 | health_condition_detail                               |
| PRJEB8347    |        3 |         3 |             0 |       34 |           4 |        2 |    216 |        70 | age_at_collection_days;sex;subject_id;timepoint_label |
| PRJNA1028158 |        1 |         1 |             0 |       10 |           1 |        1 |    114 |        38 | age_at_collection_days;sex;subject_id                 |
| PRJNA635116  |        1 |         1 |             0 |       17 |           1 |        1 |     51 |        51 | health_condition_detail                               |
| PRJEB39631   |        3 |         3 |             0 |       22 |           2 |        2 |    106 |       106 | sex                                                   |
| PRJEB49168   |        4 |         4 |             0 |       11 |           2 |        1 |    218 |       109 | age_at_collection_days;sex                            |
| PRJNA1055134 |        3 |         3 |             0 |       18 |           6 |        1 |    180 |        45 | bmi;sex;subject_id;timepoint_label                    |


Studies with zero rows: 148 (see gut_r2_per_study_shard_7.csv).

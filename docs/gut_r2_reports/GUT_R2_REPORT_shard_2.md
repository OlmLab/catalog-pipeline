# GUT R2 deterministic supplementary-table extraction — shard 2 of 8

Scope `gut_all` (config/packs/gut.yaml), route R2, src_track `gut_all_v1`, release_added `R2026.7`, package_added `1.8.0`.
Method: catalog-pipeline `gapfill_samples` R2 (exact-ID gate + header-named columns; `_supp_id_columns`, `norm_key`, `r1_parsers`)
re-driven from the shard's pmcid list instead of the infant package's `study_paper_links.csv`; all numbers below are computed from the
shard outputs. No LLM calls were made.

## Inputs
- 165 non-infant gut studies, 238 PMCIDs (≤ 4 per study), 27,213 BioSamples / 38,125 ENA runs as the exact-ID universe
  (sample_accession, secondary_sample_accession, run_accession, experiment_accession, library_name, sample_title; ids shared by > 1 sample were dropped from the join map).

## Fetch (Europe PMC `supplementaryFiles`, cache-through harvest_lib, CATALOG_CACHE_DIR in the workspace)
| outcome | PMCIDs |
|---|---|
| HTTP 200 with a supplementary ZIP | 216 |
| HTTP 200 but Europe PMC error XML ("Article … is not open access one" / empty fullTextXMLBean) | 22 |
| HTTP 500 / other failures | 0 |
| ZIP with ≥ 1 readable tabular member (xlsx/xls/csv/tsv/txt) | 99 |
| ZIP with only pdf/docx/other members | 116 |

Other member-level notes: unreadable: Error: new-line character seen in unquoted field - do you need to open the file with newline=''? (4), sheet Pacientes too large ((300000, 45)) (1), member too large (520550122 B) (1), sheet S2A_ASV annotation & abundance too large ((11382, 501)) (1), unreadable: ValueError: Sheet name is an empty list (1), sheet S4_Table too large ((269844, 17)) (1).
Total downloaded: 3.61 GB; window 2026-09-28T03:14 – 2026-09-28T04:09 UTC.

## Gate (one row per pmcid × file × sheet in `gut_r2_gate_shard_2.parquet`)
- Sheets read: 1080; exact-ID gate passed (≥ 50 % of rows or ≥ 20 exact hits): 70 sheets in 26 PMCIDs / 24 studies.
- Gate variants among passing sheets: {'raw': 70} — the prefix-stripped sample_title / library_name variant (confidence 0.8) never produced a pass, so every committed row has confidence 0.85.
- Excluded after passing: matrix-shaped sheets 24; shifted-header sheets 1 (header row one cell shorter than the populated body → column names offset; PMC9424272 `Shotgun_metadata`);
  passing non-matrix sheets with no header-named pack column: 17.
- `r2_usable` (pass ∧ ¬matrix ∧ ¬misaligned ∧ id column ∧ ≥ 1 header-named field column): **28 sheets, 15 PMCIDs, 15 studies**.

### Studies (coverage funnel)
| stage | studies |
|---|---|
| in shard | 165 |
| ≥ 1 supplementary ZIP | 156 |
| ≥ 1 readable tabular sheet | 84 |
| ≥ 1 gate-passing sheet | 24 |
| ≥ 1 usable sheet (rows extracted) | 15 |

## Extraction — `gut_r2_determinations_shard_2.parquet`
5,561 rows, 2,901 distinct samples (10.7% of the shard's BioSamples), 15 studies, 0 conflicts
(no sample × field received different values from two sheets after the shifted-header sheet was excluded; the 14 within-sheet conflicts seen before that fix came from it alone).

| field | rows | samples |
|---|---|---|
| age_at_collection_days | 862 | 862 |
| sex | 627 | 627 |
| bmi | 181 | 181 |
| country | 57 | 57 |
| health_condition_detail | 1819 | 1819 |
| antibiotic_exposure | 275 | 275 |
| subject_id | 712 | 712 |
| timepoint_label | 1028 | 1028 |

Age: bare `Age` headers were read as years (adult cohorts) — 833 rows; header-unit / text forms (29 rows, e.g. "13y 5m").
Committed ages span 1309–33603 days (median 21550 d ≈ 59 y); 0 rows ≤ 1,100 d.
Values: sex {'female': 334, 'male': 293}; antibiotic_exposure {'no': 190, 'yes': 85};
country {'CM': 57}; health_condition_detail top values {'Control': np.int64(327), 'MIND': np.int64(312), 'PD': np.int64(161), 'Family_member': np.int64(145), 'ESRD': np.int64(124), 'CPE_positive': np.int64(115), 'HC': np.int64(111), 'SD': np.int64(102)}.

### Samples per study × field
| study_accession   |   age_at_collection_days |   antibiotic_exposure |   bmi |   country |   health_condition_detail |   sex |   subject_id |   timepoint_label |
|:------------------|-------------------------:|----------------------:|------:|----------:|--------------------------:|------:|-------------:|------------------:|
| PRJDB3601         |                       71 |                     0 |    71 |         0 |                         0 |    71 |          255 |                 0 |
| PRJEB27005        |                       57 |                     0 |    56 |        57 |                         0 |    57 |           57 |                 0 |
| PRJEB31971        |                        0 |                     0 |     0 |         0 |                         0 |     3 |            0 |                 0 |
| PRJEB49334        |                        0 |                   275 |     0 |         0 |                       361 |     0 |            0 |               361 |
| PRJEB65297        |                        0 |                     0 |     0 |         0 |                       282 |     0 |            0 |                 0 |
| PRJEB65987        |                        0 |                     0 |     0 |         0 |                         0 |     0 |          140 |                 0 |
| PRJEB89837        |                       29 |                     0 |     0 |         0 |                         0 |    29 |           29 |                29 |
| PRJNA1086951      |                        0 |                     0 |     0 |         0 |                       638 |     0 |            0 |               638 |
| PRJNA1225217      |                        0 |                     0 |     0 |         0 |                        10 |     0 |            0 |                 0 |
| PRJNA533528       |                        0 |                     0 |     0 |         0 |                         0 |     0 |          231 |                 0 |
| PRJNA615162       |                      313 |                     0 |     0 |         0 |                         0 |   313 |            0 |                 0 |
| PRJNA725020       |                       54 |                     0 |    54 |         0 |                         0 |    54 |            0 |                 0 |
| PRJNA751792       |                      338 |                     0 |     0 |         0 |                       338 |     0 |            0 |                 0 |
| PRJNA849795       |                        0 |                     0 |     0 |         0 |                        40 |     0 |            0 |                 0 |
| PRJNA945504       |                        0 |                     0 |     0 |         0 |                       150 |   100 |            0 |                 0 |

### Usable sheets
| study_accession   | pmcid       | file                               | sheet                |   n_rows |   n_exact_id_hits | id_column        |   id_col_frac | header_named_field_columns                                                                 |
|:------------------|:------------|:-----------------------------------|:---------------------|---------:|------------------:|:-----------------|--------------:|:-------------------------------------------------------------------------------------------|
| PRJNA751792       | PMC13041121 | 12967_2026_7900_MOESM1_ESM.xlsx    | sample_group         |      345 |               338 | Sample           |         0.985 | age->age_at_collection_days;sex->sex;Group->health_condition_detail                        |
| PRJEB65987        | PMC11663770 | mmc1.xlsx                          | Sheet1               |      141 |               140 | ENA_ID           |         1     | Patient->subject_id                                                                        |
| PRJNA1086951      | PMC13060763 | TRC2-12-e70239-s006.xlsx           | Metadata             |      639 |               638 | #OTU ID          |         1     | Visit->timepoint_label;Group->health_condition_detail                                      |
| PRJNA1225217      | PMC13357178 | Table_1.XLSX                       | Table S1A            |       22 |                20 | Sample_ID        |         1     | Group->health_condition_detail                                                             |
| PRJNA1225217      | PMC13357178 | Table_1.XLSX                       | Table S1C            |       22 |                20 | Sample_ID        |         1     | Group->health_condition_detail                                                             |
| PRJNA1225217      | PMC13357178 | Table_1.XLSX                       | Table S1D_1          |       22 |                20 | Sample_ID        |         1     | Group->health_condition_detail                                                             |
| PRJNA1225217      | PMC13357178 | Table_2.XLSX                       | Table S2A            |       22 |                20 | Sample_ID        |         1     | Group->health_condition_detail                                                             |
| PRJNA1225217      | PMC13357178 | Table_2.XLSX                       | Table S2B            |       42 |                20 | Sample_ID        |         1     | Group->health_condition_detail                                                             |
| PRJNA1225217      | PMC13357178 | Table_2.XLSX                       | Table S2C_1          |       42 |                20 | Sample_ID        |         1     | Group->health_condition_detail                                                             |
| PRJNA725020       | PMC10653893 | mbio.01511-23-s0001.xlsx           | Tab 3                |      115 |                54 | Subject          |         0.478 | Subject->subject_id;Sex->sex;Age->age_at_collection_days;BMI->bmi                          |
| PRJNA849795       | PMC10729956 | pone.0292645.s001.xlsx             | Data                 |       41 |               120 | Index            |         1     | Group->health_condition_detail                                                             |
| PRJDB3601         | PMC4833420  | supp_dsw002_dsw002supp_tables.xlsx | S1                   |      109 |                71 | Subject ID       |         0.67  | Subject ID->subject_id;Age->age_at_collection_days;Sex->sex;BMI->bmi                       |
| PRJDB3601         | PMC4833420  | supp_dsw002_dsw002supp_tables.xlsx | S12                  |      403 |               400 | Accession number |         1     | Individual->subject_id                                                                     |
| PRJNA615162       | PMC7919092  | 13073_2021_853_MOESM1_ESM.xlsx     | Table S1             |      315 |               313 | Sample           |         1     | Sex->sex;Age->age_at_collection_days                                                       |
| PRJNA533528       | PMC6807385  | mgen-5-293-s002.xlsx               | Table S1             |      243 |               231 | Sample           |         0.979 | Patient->subject_id                                                                        |
| PRJNA533528       | PMC6807385  | mgen-5-293-s002.xlsx               | Table S3             |      238 |               231 | ID               |         0.979 | Patient->subject_id                                                                        |
| PRJEB89837        | PMC12775388 | 41598_2025_29896_MOESM2_ESM.xlsx   | TableS1              |       31 |                87 | libID            |         1     | participant->subject_id;Baseline=A,12weeks=B->timepoint_label;Sex                          |
|                   |             |                                    |                      |          |                   |                  |               | 1-male                                                                                     |
|                   |             |                                    |                      |          |                   |                  |               | 2-female->sex;Age                                                                          |
| PRJEB65297        | PMC10571392 | 13059_2023_3056_MOESM1_ESM.xlsx    | TS3                  |      716 |               282 | Sample ID        |         0.394 | Sample group->health_condition_detail                                                      |
| PRJEB49334        | PMC9519440  | 41564_2022_1221_MOESM12_ESM.xlsx   | 1a                   |      363 |               361 | Index            |         0.997 | Status->health_condition_detail                                                            |
| PRJEB49334        | PMC9519440  | 41564_2022_1221_MOESM12_ESM.xlsx   | 1b                   |      363 |               361 | Index            |         0.997 | Status->health_condition_detail                                                            |
| PRJEB49334        | PMC9519440  | 41564_2022_1221_MOESM9_ESM.xlsx    | 1a                   |      363 |               361 | Index            |         0.997 | Status->health_condition_detail                                                            |
| PRJEB49334        | PMC9519440  | 41564_2022_1221_MOESM9_ESM.xlsx    | 1b                   |      348 |               345 | Index            |         0.994 | Visit.ID->timepoint_label;Subject.Code->subject_id;Antibiotics.since.last.visit->antibioti |
| PRJEB49334        | PMC9519440  | 41564_2022_1221_MOESM13_ESM.xlsx   | 2a                   |      363 |               361 | Index            |         0.997 | Status->health_condition_detail                                                            |
| PRJEB49334        | PMC9519440  | 41564_2022_1221_MOESM16_ESM.xlsx   | abundances           |      553 |               361 | tag              |         0.997 | timepoint->timepoint_label                                                                 |
| PRJEB31971        | PMC6854460  | mmc5.xlsx                          | Ancient_read_mapping |       10 |                 5 | Illumina run ID  |         0.714 | Genetic sex->sex                                                                           |
| PRJNA945504       | PMC13354076 | pone.0340748.s016.xlsx             | S5_Table             |      715 |                24 | Accession_Number |         1     | Phenotype->health_condition_detail                                                         |
| PRJNA945504       | PMC13354076 | pone.0340748.s012.xlsx             | S1_Table             |      151 |               150 | Accession_number |         1     | Phenotype->health_condition_detail;Gender->sex                                             |
| PRJEB27005        | PMC6364966  | pone.0211139.s001.xlsx             | S1                   |      141 |                57 | Sample           |         0.413 | Subject->subject_id;Country->country;Sex->sex;Age->age_at_collection_days;BMI->bmi         |

## Header map — `gut_supp_header_map_shard_2.csv`
3729 distinct normalised headers were met in gate-passing, non-matrix sheets; 22 map to a pack field
(infant field map 11, gut regex rules 5, manual decisions 6).

| header_norm                  | field_name              | parser            |   unit_default |   n_sheets | source           |
|:-----------------------------|:------------------------|:------------------|---------------:|-----------:|:-----------------|
| group                        | health_condition_detail | text              |            nan |          9 | gut_rule         |
| status                       | health_condition_detail | text              |            nan |          4 | gut_rule         |
| bmi                          | bmi                     | bmi_numeric       |            nan |          3 | gut_rule         |
| individual                   | subject_id              | identifier        |            nan |          1 | gut_rule         |
| age_year_and_months          | age_at_collection_days  | age_bare          |            nan |          1 | manual           |
| sample_group                 | health_condition_detail | text              |            nan |          1 | gut_rule         |
| age                          | age_at_collection_days  | age_bare          |            nan |          5 | infant_field_map |
| sex                          | sex                     | categorical_sex   |            nan |          5 | infant_field_map |
| patient                      | subject_id              | identifier        |            nan |          3 | infant_field_map |
| subject                      | subject_id              | identifier        |            nan |          2 | infant_field_map |
| phenotype                    | health_condition_detail | text              |            nan |          2 | manual           |
| visit                        | timepoint_label         | label             |            nan |          1 | infant_field_map |
| subject_id                   | subject_id              | identifier        |            nan |          1 | infant_field_map |
| participant                  | subject_id              | identifier        |            nan |          1 | infant_field_map |
| visit_id                     | timepoint_label         | label             |            nan |          1 | infant_field_map |
| timepoint                    | timepoint_label         | label             |            nan |          1 | infant_field_map |
| gender                       | sex                     | categorical_sex   |            nan |          1 | infant_field_map |
| country                      | country                 | country           |            nan |          1 | infant_field_map |
| baseline_a_12weeks_b         | timepoint_label         | label             |            nan |          1 | manual           |
| sex_1_male_2_female          | sex                     | sex_coded_1m_2f   |            nan |          1 | manual           |
| antibiotics_since_last_visit | antibiotic_exposure     | categorical_yesno |            nan |          1 | manual           |
| genetic_sex                  | sex                     | categorical_sex   |            nan |          1 | manual           |

### Skipped headers (top, excluding taxon / pathway / OTU / assembly-statistic columns)
| header_norm               |   n_sheets | decision                                                                                                  |
|:--------------------------|-----------:|:----------------------------------------------------------------------------------------------------------|
| sample_id                 |          9 | no rule                                                                                                   |
| sample                    |          7 | no rule                                                                                                   |
| index                     |          6 | no rule                                                                                                   |
| pcoa1                     |          5 | no rule                                                                                                   |
| pcoa2                     |          5 | no rule                                                                                                   |
| accession_number          |          4 | no rule                                                                                                   |
| substatus                 |          4 | skipped (manual): finer coding of 'status' in the same sheet; status column kept                          |
| type                      |          3 | no rule                                                                                                   |
| sample_name               |          3 | no rule                                                                                                   |
| clust                     |          3 | no rule                                                                                                   |
| richness                  |          3 | no rule                                                                                                   |
| quartile                  |          2 | no rule                                                                                                   |
| run_accession             |          2 | no rule                                                                                                   |
| cohort                    |          2 | skipped (manual): ambiguous: disease groups in one sheet (Controls/SSc/IgG4RD), cities in another (BJ/SH) |
| viral_realm               |          2 | no rule                                                                                                   |
| input_file                |          2 | no rule                                                                                                   |
| distance_metric           |          2 | no rule                                                                                                   |
| pcoa1_percent             |          2 | no rule                                                                                                   |
| shannon                   |          2 | no rule                                                                                                   |
| evenness                  |          2 | no rule                                                                                                   |
| id                        |          2 | no rule                                                                                                   |
| pcoa2_percent             |          2 | no rule                                                                                                   |
| subject_code              |          1 | skipped (guard): <5 distinct values over >=20 rows — role code (T/F1/F2/F3), not an identifier            |
| strain_id                 |          1 | no rule                                                                                                   |
| original_id               |          1 | no rule                                                                                                   |
| sample_accession          |          1 | no rule                                                                                                   |
| liver_disorder            |          1 | no rule                                                                                                   |
| fibrosis_stage            |          1 | skipped (manual): stage, not a condition                                                                  |
| environmental_medium      |          1 | no rule                                                                                                   |
| body_site                 |          1 | no rule                                                                                                   |
| sequencing_platform       |          1 | no rule                                                                                                   |
| libid                     |          1 | no rule                                                                                                   |
| non_human_r2              |          1 | no rule                                                                                                   |
| eremothecium_unclassified |          1 | no rule                                                                                                   |
| candida_glabrata          |          1 | no rule                                                                                                   |
| naumovozyma_unclassified  |          1 | no rule                                                                                                   |
| saccharomyces_cerevisiae  |          1 | no rule                                                                                                   |
| candida_albicans          |          1 | no rule                                                                                                   |
| candida_dubliniensis      |          1 | no rule                                                                                                   |
| candida_unclassified      |          1 | no rule                                                                                                   |

## Guards applied (deterministic, logged in parse_note / header map)
- id join only on ids unique to one BioSample; one column per field per sheet; identical duplicate values collapse, disagreeing ones are dropped and logged.
- age 0–120 y; bmi 10–80; sex only from explicit tokens (or a header that defines the code, e.g. `sex_1_male_2_female`); health_condition_detail requires ≥ 2 letters (numeric codes without a legend are skipped);
  identifier columns with < 5 distinct values over ≥ 20 rows are role codes, not subject ids (`Subject.Code` T/F1/F2/F3 dropped, 345 rows).
- leading Excel apostrophes stripped from values; quotes ≤ 12 words (0 violations).

## Deviations / caveats
- Concurrency: a superseded fetch process could not be terminated inside the sandbox (no signal permission), so for ~50 min two fetchers (2 workers each = 4 connections) ran against Europe PMC instead of ≤ 2; both wrote the same cache, no duplicate downloads.
- Retry policy: one back-off retry on 429/5xx (max_retries=2) instead of harvest_lib's default 5; no 5xx occurred.
- Members > 60 MB (1: 520 MB), sheets > 300,000 rows (3) and > 4 M cells (1) were skipped; 4 csv/txt members failed to parse (embedded newlines); 1 xlsx had an empty sheet list.
- Only header-named columns were read; group/status/phenotype headers were committed as raw text for downstream coding, as instructed; ambiguous headers (cohort, substatus, antibiotic_names, …) were skipped and listed.

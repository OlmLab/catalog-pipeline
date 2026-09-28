# GUT_R2_REPORT — shard 0 (deterministic supplementary-table extraction, scope gut_all)

Generated 2026-09-28T04:41:59Z. Fetch complete: True. LLM calls: 0 (deterministic header-named extraction only).

## Coverage

| metric | value |
|---|---|
| studies in shard | 165 |
| PMCIDs (own-data / uncontested papers) | 226 |
| PMCID fetch status counts | {'200': 226} |
| PMCIDs with a supplementary zip | 209 |
| PMCIDs whose zip has ≥ 1 tabular file (xlsx/xls/csv/tsv/txt) | 118 |
| PMCIDs with docx/pdf supplements only (not read by R2) | 73 |
| studies with ≥ 1 zip | 154 |
| studies with ≥ 1 tabular file | 98 |
| studies with ≥ 1 gate-passing sheet | 33 |
| studies with ≥ 1 r2-usable sheet (gate + header-named field column, not a matrix) | 22 |
| studies with ≥ 1 determination row | 22 |
| sheets read | 1548 |
| sheets passing the exact-ID gate (either variant) | 111 |
| … of which via the prefix-stripped variant (confidence 0.8) | 0 |
| r2-usable sheets | 47 |
| determination rows | 8864 |
| conflicts logged | 677 ({'across_sheets': 413, 'within_sheet': 264}) |

## Rows and samples per field

| field | rows | samples | studies |
|---|---|---|---|
| age_at_collection_days | 1613 | 1613 | 11 |
| sex | 1613 | 1613 | 11 |
| bmi | 451 | 451 | 6 |
| country | 887 | 887 | 2 |
| health_condition_detail | 241 | 241 | 2 |
| antibiotic_exposure | 1124 | 1124 | 5 |
| subject_id | 1800 | 1800 | 10 |
| timepoint_label | 1135 | 1135 | 9 |

## Conflicts by field

{'age_at_collection_days': 335, 'antibiotic_exposure': 147, 'health_condition_detail': 101, 'timepoint_label': 58, 'subject_id': 36}

## Studies with rows (top 25)

| study_accession   |   n_rows |   n_samples | fields                                                                            |
|:------------------|---------:|------------:|:----------------------------------------------------------------------------------|
| PRJNA698223       |     3841 |         710 | age_at_collection_days;antibiotic_exposure;country;sex;subject_id;timepoint_label |
| PRJEB81804        |     1390 |         278 | age_at_collection_days;antibiotic_exposure;country;sex;subject_id                 |
| PRJEB41481        |      600 |         420 | health_condition_detail;subject_id                                                |
| PRJNA918651       |      500 |         100 | age_at_collection_days;bmi;sex;subject_id;timepoint_label                         |
| PRJNA752006       |      360 |         180 | age_at_collection_days;sex                                                        |
| PRJNA890008       |      354 |         118 | age_at_collection_days;bmi;sex                                                    |
| PRJNA557323       |      300 |         100 | age_at_collection_days;bmi;sex                                                    |
| PRJNA491335       |      264 |         208 | subject_id;timepoint_label                                                        |
| PRJNA646752       |      246 |          82 | antibiotic_exposure;subject_id;timepoint_label                                    |
| PRJEB109268       |      150 |          30 | age_at_collection_days;bmi;sex;subject_id;timepoint_label                         |
| PRJNA801448       |      149 |          74 | antibiotic_exposure;bmi;subject_id                                                |
| PRJNA982563       |      121 |         121 | timepoint_label                                                                   |
| PRJNA1157583      |      102 |          51 | age_at_collection_days;sex                                                        |
| PRJNA678871       |      100 |         100 | timepoint_label                                                                   |
| PRJNA597839       |       90 |          30 | age_at_collection_days;bmi;sex                                                    |
| PRJEB47061        |       84 |          84 | antibiotic_exposure;health_condition_detail                                       |
| PRJNA1008138      |       68 |          68 | subject_id                                                                        |
| PRJNA885137       |       53 |          53 | subject_id                                                                        |
| PRJNA637878       |       49 |          49 | timepoint_label                                                                   |
| PRJNA362284       |       24 |          12 | age_at_collection_days;sex                                                        |
| PRJNA836336       |       11 |          11 | timepoint_label                                                                   |
| PRJNA602101       |        8 |           4 | age_at_collection_days;sex                                                        |

## Top skipped headers on usable sheets (ambiguous / unmapped — listed, not extracted)

| header_norm                           | parser    | reason                                                                                                                      |   n_sheets |   n_values | example            |
|:--------------------------------------|:----------|:----------------------------------------------------------------------------------------------------------------------------|-----------:|-----------:|:-------------------|
| length_of_stay_in_days                | UNMAPPED  | no rule                                                                                                                     |         15 |       4720 | 21                 |
| traveler_type                         | UNMAPPED  | no rule                                                                                                                     |         15 |       5565 | TD                 |
| region                                | AMBIGUOUS | sub-national / ambiguous location                                                                                           |         13 |       4186 | North America      |
| sample_type                           | AMBIGUOUS | header meaning not decidable from the name                                                                                  |         11 |       3270 | colon mucosa       |
| sample_code                           | UNMAPPED  | no rule                                                                                                                     |         11 |       3496 | A                  |
| total_duration_in_days                | UNMAPPED  | no rule                                                                                                                     |          5 |        992 | 60                 |
| length_of_stay_in_wks                 | UNMAPPED  | no rule                                                                                                                     |          5 |       2489 | 1                  |
| stool_grade                           | UNMAPPED  | no rule                                                                                                                     |          5 |       1513 | Grade-2            |
| group                                 | AMBIGUOUS | group header mixes disease, treatment arm and timepoint semantics (observed: 'T-1_Fh', 'Dust'); left to downstream curation |          4 |        298 | Case               |
| baseline_shannon                      | UNMAPPED  | no rule                                                                                                                     |          4 |        959 | 2.549623842892756  |
| comp_id                               | UNMAPPED  | no rule                                                                                                                     |          4 |        959 | P002S01-P002S02    |
| baseline_richness                     | UNMAPPED  | no rule                                                                                                                     |          4 |        959 | 52                 |
| total_rpkm_log                        | UNMAPPED  | no rule                                                                                                                     |          4 |       1061 | 2.9362816343291964 |
| bray_sim                              | UNMAPPED  | no rule                                                                                                                     |          4 |        959 | 0.8374800929015029 |
| jacd_sim                              | UNMAPPED  | no rule                                                                                                                     |          4 |        959 | 0.72040064672247   |
| alistipes_shahii                      | UNMAPPED  | no rule                                                                                                                     |          3 |       1426 | 0                  |
| bacteroides_salyersiae                | UNMAPPED  | no rule                                                                                                                     |          3 |       1426 | 0                  |
| bacteroides_thetaiotaomicron          | UNMAPPED  | no rule                                                                                                                     |          3 |       1426 | 0                  |
| bacteroides_uniformis                 | UNMAPPED  | no rule                                                                                                                     |          3 |       1426 | 0                  |
| bacteroides_vulgatus                  | UNMAPPED  | no rule                                                                                                                     |          3 |       1426 | 0                  |
| cohort                                | AMBIGUOUS | header meaning not decidable from the name                                                                                  |          3 |       1083 | mSTUDY             |
| coprobacter_fastidiosus               | UNMAPPED  | no rule                                                                                                                     |          3 |       1426 | 0                  |
| escherichia_coli                      | UNMAPPED  | no rule                                                                                                                     |          3 |       1426 | 0.11087            |
| sample_source                         | UNMAPPED  | no rule                                                                                                                     |          3 |       1493 | Chicken carcass    |
| shigella_sonnei                       | UNMAPPED  | no rule                                                                                                                     |          3 |       1426 | 0                  |
| barnesiella_intestinihominis          | UNMAPPED  | no rule                                                                                                                     |          3 |       1426 | 0                  |
| streptococcus_infantis                | UNMAPPED  | no rule                                                                                                                     |          3 |       1426 | 0.00334            |
| shannon                               | UNMAPPED  | no rule                                                                                                                     |          3 |        846 | 2.549623842892756  |
| alistipes_putredinis                  | UNMAPPED  | no rule                                                                                                                     |          3 |       1426 | 0                  |
| bacteroides_nordii                    | UNMAPPED  | no rule                                                                                                                     |          3 |       1426 | 0                  |
| episode_id                            | UNMAPPED  | no rule                                                                                                                     |          3 |        513 | TD0002_1           |
| bacteroides_massiliensis              | UNMAPPED  | no rule                                                                                                                     |          3 |       1426 | 0                  |
| enterococcus_durans                   | UNMAPPED  | no rule                                                                                                                     |          3 |       1426 | 0                  |
| bacteroides_fragilis                  | UNMAPPED  | no rule                                                                                                                     |          3 |       1426 | 0                  |
| rel_d_days                            | UNMAPPED  | no rule                                                                                                                     |          3 |        513 | -5                 |
| dorea_formicigenerans                 | UNMAPPED  | no rule                                                                                                                     |          3 |       1426 | 2.2404             |
| coprococcus_sp_art55_1                | UNMAPPED  | no rule                                                                                                                     |          3 |       1426 | 0                  |
| condition                             | AMBIGUOUS | bare 'condition' mixes disease and storage/experimental condition (observed: 'RNAlater', 'FLOQSwab')                        |          3 |     148047 |                    |
| sample_code_a_non_diarrhea_d_diarrhea | UNMAPPED  | no rule                                                                                                                     |          3 |        861 | A                  |
| rothia_mucilaginosa                   | UNMAPPED  | no rule                                                                                                                     |          3 |       1426 | 0                  |

## Method

- Europe PMC `supplementaryFiles` zip per PMCID via harvest_lib.fetch (cache in the workspace), ≤ 2 concurrent, max 3 attempts with exponential backoff on 429/5xx; nested .zip members expanded one level.
- Sheets: xlsx/xls (all sheets), csv/tsv/txt (sniffed separator); header row = first row with ≥ 50 % non-empty cells (gapfill_samples._supp_id_columns).
- Exact-ID gate (gapfill_samples.r2_gate logic re-implemented for the pmcids input): ≥ 20 unique exact hits or ≥ 50 % of data rows hitting the study's own BioSample / secondary sample / run / experiment / library_name / sample_title values; only values that identify exactly one BioSample are join keys; matrix sheets (ids in header, > 90 % numeric body, > 20 cols) excluded.
- Prefix-stripped variant (only when the raw gate fails): sample_title / library_name after removing their study-wide common prefix, and sheet columns after removing their common prefix; rows get confidence 0.8 and `gate_variant=prefix_stripped`.
- Header → field map: config/attribute_field_map.csv semantics extended by regex rules in gut_r2.py (HEADER_RULES); bare `Age` = years for these non-infant cohorts unless an age-units column is present (guard: 0–120 y); age ranges are not values; numeric-coded group/sex columns without a legend are skipped; country accepted only on exact pycountry / fix lookups.
- Parsers: r1_parsers (age, sex, yes/no incl. drug names → yes, country); bmi numeric in [10, 80]; health_condition_detail = raw cell text (≤ 120 chars), code assigned downstream.
- One row per (sample, field): within-sheet disagreements dropped, across-sheet disagreements resolved to the sheet with more exact hits; all logged in gut_r2_log_shard_0.json.

## Decisions and caveats (this shard)

- All 226 PMCIDs returned HTTP 200 from the Europe PMC supplementaryFiles endpoint (no 500s on this shard); 17 returned an EPMC errorBean (no supplementary files) and 73 zips hold only docx/pdf supplements, which the deterministic R2 does not read (pipeline route pdfdocx_extract; out of this task's scope).
- Prefix-stripped join variant: an initial version passed 31 sheets, all false joins (short numeric remainders such as '1'..'50' matching peptide / BLAST tables). After requiring identifier-like remainders (≥ 4 chars, or ≥ 3 with a letter) and the ≥ 50 % gate only, 0 sheets pass on this shard; no confidence-0.8 rows were emitted.
- Header decisions taken on observed values (gut_supp_header_map_shard_0.csv): bare `condition` moved to AMBIGUOUS (one sheet meant Parkinson/Control, another meant storage kit — RNAlater/FLOQSwab); `group`/`study_group`/`arm` moved to AMBIGUOUS (values such as 'T-1_Fh', 'Dust'); a `subject`-type header whose values look like sequence accessions (BLAST 'subject', 'gi|…') is skipped. Bare `Age` = years (all cohorts in this shard are non-infant; guard 0–120 y), a units column (`host_age_units`) overrides.
- Conflicts: 335 across-sheet age disagreements come from one study (PRJNA698223, Nat Commun MOESM7) whose sheet SD13 reuses the header `Age` for a fractional-year quantity; the sheet with the most exact ID hits (SD05) was kept, as specified. Within-sheet disagreements (long-format tables with several rows per sample, e.g. PRJEB47061 per-drug antibiotic rows) were dropped, not resolved.
- health_condition_detail is raw text (≤ 120 chars); vocabulary codes are assigned downstream. Values are exactly what the cell says (e.g. 'IBD', 'Control').
- No LLM calls were made.

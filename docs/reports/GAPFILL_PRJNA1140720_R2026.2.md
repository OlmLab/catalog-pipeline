# GAPFILL_PRJNA1140720_REPORT — new samples in an included study (release R2026.2, package 1.4.0)

## 1. Harvest
* BioSamples: 150 new; found 150 (ENA XML 150, NCBI efetch fallback 0, missing 0); 3900 attribute rows; 150 experiment records.
* Attribute keys (n samples): `age` 150, `alias` 150, `biosamplemodel` 150, `center_name` 150, `collection_date` 150, `ena_first_public` 150, `ena_last_update` 150, `family_id` 150, `geo_loc_name` 150, `host` 150, `insdc_secondary_accession` 150, `isolation_source` 150, `lat_lon` 150, `n_of_bases` 150, `ncbi_submission_package` 150, `organism` 150, `participant_type` 150, `sample_name_scientific_name` 150, `sample_name_taxon_id` 150, `sample_type` 150, `secondary_id` 150, `sex` 150, `subjectid` 150, `submitter_id` 150, `timepoint` 150, `title` 150

## 2. Comparison with the study's existing samples
* keys only in the new samples: age, sex, subjectid, timepoint
* keys only in the existing samples: during_atb_atf, during_or_post_atb_atf, n_of_reads, nursery, nursery_groups, participant_id, pet_in_family, sibling_in_family, subject_id, time_point, time_point_collapsed
* `participant_type`: existing {'Baby': 652, 'Mother': 151, 'Father': 110, 'Educator': 69, 'Sibling': 20, 'Pet': 11} → new {'Mother': 81, 'Father': 62, 'Sibling': 7}
* `sample_type`: existing {'Fecal': 1013} → new {'oral': 150}
* `isolation_source`: existing {'feces': 1013} → new {'saliva': 150}
* `organism`: existing {'human gut metagenome': 1013} → new {'human saliva metagenome': 150}
* `host`: existing {'Homo sapiens': 1013} → new {'homo_sapiens': 150}
* `title`: existing {'Metagenome or environmental sample from human gut metagenome': 1013} → new {'Metagenome or environmental sample from human saliva metagenome': 150}

* existing wide-table classes: {"body_site_class": {"primary": 1013}, "age_scope": {"age_unknown_no_study_estimate": 652, "non_infant_role": 361}, "catalog_scope": {"False": 1013}, "role": {"infant": 652, "other": 210, "mother": 151}, "role_source": {"attr_role": 1013}, "adult_age_flag": {"False": 1013}, "sample_unit": {"biosample": 1013}}
* existing group-scope (R3/R4 cohort_default) rows: 0

## 3. Extraction
* committed determinations: 749 — age_at_collection_days 149, country 150, sex 150, subject_id 150, timepoint_label 150
* superseded (lower-precedence duplicates within R1): 300; rejected (no value / validator): 1; sentinels (sample × field without evidence): 2101
* ages committed under the v1.2 `out_of_scope_adult` convention (> 1,100 d; evidence for adult_age_flag): 145
* validator pass rate on committed rows: 100.0% (every committed row passed validate_row; out-of-range ages pass every check except the in-scope range, by convention)
* unit resolution: U1/U2 rules [{"study_accession": "PRJNA1140720", "attr_key": "age", "n": 150, "unit": null, "rule": null, "evidence": null, "median": 36.0, "max": 50.0, "frac_le36": 0.5333333333333333}]; U3 adopted: [{'sheet': '41586_2025_9983_MOESM1_ESM.xlsx[ST3]', 'id_column': 'participant_id', 'join': 'subject_attr_digits', 'age_column': 'age_months', 'table_unit': 'months', 'candidate_unit': 'years', 'n_matched': 150, 'frac_agree': 0.993, 'adopted': True, 'corroboration': 'participant_type', 'evidence': 'paper.supp.41586_2025_9983_MOESM1_ESM.xlsx[ST3!age_months] participant_id join (subject_attr_digits); participant_type agrees; n=150 agree=0.993', 'n_samples_corroborated': 149}]
* composite subject ids: {'n_composite': 150, 'frac_matching_existing_subject_ids': 0.9933, 'n_in_library_name': 148}
* group rows extended from existing cohort_default statements: 0

### R2 supplementary-table gate
| pmcid       | file                            | sheet           |   n_rows |   n_cols |   n_exact_id_hits |   frac_new_ids_hit | passes_exact_gate   | is_matrix   | header_named_field_columns                     | r2_usable   |
|:------------|:--------------------------------|:----------------|---------:|---------:|------------------:|-------------------:|:--------------------|:------------|:-----------------------------------------------|:------------|
| PMC12960237 | 41586_2025_9983_MOESM1_ESM.xlsx | Overview of STs |       15 |        2 |                 0 |              0     | False               | False       |                                                | False       |
| PMC12960237 | 41586_2025_9983_MOESM1_ESM.xlsx | ST1             |       18 |        8 |                 0 |              0     | False               | False       |                                                | False       |
| PMC12960237 | 41586_2025_9983_MOESM1_ESM.xlsx | ST2             |     1014 |       13 |                 0 |              0     | False               | False       | participant_id;time_point;time_point_collapsed | False       |
| PMC12960237 | 41586_2025_9983_MOESM1_ESM.xlsx | ST3             |      136 |       16 |                 0 |              0     | False               | False       | participant_id;age_months                      | False       |
| PMC12960237 | 41586_2025_9983_MOESM1_ESM.xlsx | ST4             |     1014 |     2918 |                 0 |              0     | False               | False       |                                                | False       |
| PMC12960237 | 41586_2025_9983_MOESM1_ESM.xlsx | ST5             |     1014 |     1014 |                 0 |              0     | False               | False       |                                                | False       |
| PMC12960237 | 41586_2025_9983_MOESM1_ESM.xlsx | ST6             |       12 |        7 |                 0 |              0     | False               | False       |                                                | False       |
| PMC12960237 | 41586_2025_9983_MOESM1_ESM.xlsx | ST7             |     1014 |     1406 |                83 |              0.553 | True                | True        |                                                | False       |
| PMC12960237 | 41586_2025_9983_MOESM1_ESM.xlsx | ST8             |     1014 |     1406 |                83 |              0.553 | True                | False       |                                                | False       |
| PMC12960237 | 41586_2025_9983_MOESM1_ESM.xlsx | ST9             |       13 |        5 |                 0 |              0     | False               | False       | Timepoint                                      | False       |
| PMC12960237 | 41586_2025_9983_MOESM1_ESM.xlsx | ST10            |       18 |        4 |                 0 |              0     | False               | False       | Timepoint                                      | False       |
| PMC12960237 | 41586_2025_9983_MOESM1_ESM.xlsx | ST11            |       16 |        7 |                 0 |              0     | False               | False       | Timepoint                                      | False       |
| PMC12960237 | 41586_2025_9983_MOESM1_ESM.xlsx | ST12            |        7 |       10 |                 0 |              0     | False               | False       |                                                | False       |
| PMC12960237 | 41586_2025_9983_MOESM1_ESM.xlsx | ST13            |       66 |       11 |                 0 |              0     | False               | False       |                                                | False       |
| PMC12960237 | 41586_2025_9983_MOESM1_ESM.xlsx | ST14            |      157 |       11 |                 0 |              0     | False               | False       |                                                | False       |
* R2 rows committed: 0 (no R2 source)

## 4. Subjects
* subjects resolved: 150/150; subject_keys already present in the study: 149; roles: {'mother': 81, 'other': 69}; role_source: {'attr_role': 150}
* mothers linked to an infant subject: 81/81; t_basis: {'timepoint_label': 130, 'single_sample': 20}

## 5. Sandpiper (per-run API delta)
* {"enabled": true, "n_runs": 150, "n_api_calls": 150, "n_in_sandpiper": 0, "n_profiles": 0, "errors": 0, "api_note": "api_checked_per_run"}

## 6. Wide table
* rows 150; body_site_class {'excluded': 150}; age_scope {'adult_flagged': 145, 'non_infant_role': 5}; role {'mother': 81, 'other': 69}; catalog_scope 0; adult_age_flag 145
* n_fields_with_value: {4: 1, 5: 149}

## 7. Study-level delta (before → after)
| metric | before | after |
|---|---|---|
| n_samples | 1013 | 1163 |
| n_runs | 1013 | 1163 |
| n_biosamples | 1013 | 1163 |
| n_sample_rows | 1013 | 1163 |
| n_infant_scope_samples | 1013 | 1013 |
| n_body_site_excluded | 0 | 150 |
| n_catalog_scope | 0 | 0 |
| n_age_scope_infant | 0 | 0 |
| n_adult_flagged | 0 | 145 |
| n_non_infant_role | 361 | 366 |
| n_infant_evidenced | 0 | 0 |
| n_study_all_infant | 0 | 0 |
| n_age_unknown_mixed_study | 0 | 0 |
| n_age_unknown_no_study_estimate | 652 | 652 |
| n_mothers | 151 | 232 |
| n_infant_role_samples | 652 | 652 |
| sp_n_samples_profiled | 935 | 935 |
| sp_frac_samples_profiled | 0.923 | 0.804 |
| sp_n_runs_profiled | 935 | 935 |
| sp_frac_runs_profiled | 0.923 | 0.804 |
| cov_probiotic_exposure | 0.0 | 0.0 |
| cov_preterm_status | 0.0 | 0.0 |
| cov_gestational_age_weeks | 0.0 | 0.0 |
| cov_delivery_mode | 0.0 | 0.0 |
| cov_feeding_mode | 0.0 | 0.0 |
| cov_antibiotic_exposure | 0.0 | 0.0 |
| cov_age_at_collection_days | 0.0 | 0.128117 |
| cov_birth_weight_grams | 0.0 | 0.0 |
| cov_country | 1.0 | 1.0 |
| cov_maternal_antibiotics | 0.0 | 0.0 |
| cov_hmo_supplementation | 0.0 | 0.0 |
| cov_nec_status | 0.0 | 0.0 |
| cov_health_condition | 0.0 | 0.0 |
| cov_multiple_birth | 0.0 | 0.0 |
| cov_sibling_in_study | 0.6436327739387957 | 0.560619 |
| cov_geo_subregion | 0.0 | 0.0 |

## 8. Deviations

## 9. Curator notes for the R2026.2 run (written by the agent that ran it; every number above is read from the tables)
* **The 150 new samples are not infant stool.** Attributes: `isolation_source=saliva`, `sample_type=oral`, organism `human saliva metagenome`, `participant_type` Mother 81 / Father 62 / Sibling 7; the existing 1,013 rows are `feces` from Baby 652 / Mother 151 / Father 110 / Educator 69 / Sibling 20 / Pet 11. Hence `body_site_class=excluded` (scope_constants BODY_SITE_EXCLUDE: saliva/oral) for all 150, `catalog_scope=False`, and the study's headline counts do not move (n_catalog_scope 0 → 0; n_infant_scope_samples 1013 → 1013).
* **Differences from the existing rows, and how they were handled.** (i) New keys `age`, `sex`, `subjectid`, `timepoint` (existing: `subject_id`, `time_point`, no age/sex) — same field map (`config/attribute_field_map.csv`), so `sex` is committed for the new rows only (the existing rows have no sex attribute). (ii) `subjectid` lacks the family prefix the existing `subject_id` carries (`B1_FA5000`); the composite `<family_id>_<subjectid>` matches 149/150 existing subject ids and is carried by 148/150 library names, so subject_id is committed as the composite (evidence `sample.attr.subjectid`, quote names both attributes) and 149/150 new rows join an existing subject_key; the one exception (`B5_MO5010`) is a new subject whose family_id also disagrees with the paper's ST3 — flagged for the curator. (iii) Evidence labels follow the current convention `sample.attr.<key>` (the study's 2026-09 rows still carry the pre-labelled `biosample_attr`). (iv) ENA read_run `country` is empty for the new runs (the existing rows used it); country comes from `sample.attr.geo_loc_name=Italy` (IT) instead.
* **Ages.** `age` is a bare number (30–50 for parents, 2–22 for siblings). U1/U2 cannot fix the unit (days and weeks both admissible). U3: the linked paper's ST3 (`age_months` per `participant_id`) agrees with `age` in years for 149/150 samples (participant_type agrees 150/150). 145 ages > 1,100 d are committed under the v1.2 `out_of_scope_adult` convention (→ `adult_age_flag`, `age_scope=adult_flagged`; roles mother/other kept from `participant_type`, as in the existing catalog); 4 sibling samples are ≤ 1,100 d (SI5025 730 d ×2, SI5033 1,096 d, SI1033 1,096 d) but keep `age_scope=non_infant_role` by the documented precedence (role other from attr_role) — a curator may want to look at these 3 under-3 siblings (saliva, so out of body-site scope anyway). 1 sample (`B5_MO5010`, age=43 vs ST3 30.6 y) disagrees and stays a sentinel.
* **R2:** own-data paper PMC12960237 supplementary xlsx — ST7/ST8 (strain-sharing matrices) list 83 of the 150 library names as column headers but carry no metadata; ST2 (per-sample metadata) covers only the 1,013 fecal samples. No R2 field values ('no R2 source'). ST3 was used solely for the U3 unit check. No R3/R4 group statements exist for this study, so none were extended.
* **Sandpiper:** all 150 runs checked via `api/metadata/<run>`; none present (server message: the run list was gathered 3 March 2026). `sp_miss_reason=published_after_snapshot_horizon` (first_public 2026-09-02 > 2026-03-22). Study sp_frac_samples_profiled 0.923 → 0.804.
* **ENA run statistics:** `read_count`/`base_count` are 0 for all 150 runs in ENA read_run (files not yet mirrored); `runs_new.parquet` keeps the ENA values; the submitter-provided `n_of_bases` attribute exists in the attribute table.
* **Subjects/timepoints:** t_index/n_timepoints_subject of the new rows are computed within the new saliva series (T01–T03; year-granular ages cannot order timepoints → basis timepoint_label, as in the existing rows). Existing rows are not rewritten (apply_gapfill asserts this), so an existing mother's n_timepoints_subject does not count her new saliva samples.

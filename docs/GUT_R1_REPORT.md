# GUT_R1_REPORT — R1 attribute extraction for scope `gut_all` (src_track gut_all_v1, release R2026.7, package 1.8.0)

Generated 2026-09-27 from `gut_attributes_nonInfant.parquet` (9,411,229 attribute rows; 437,184 BioSamples; 2,427 studies with ≥1 attribute row of the 2,448 non-infant gut studies) and `gut_attribute_keys.csv` (4,936 keys). Deterministic parsers only; the utility model classified KEYS (never values). catalog-pipeline commit 6568731.

## Deliverables
- `gut_attribute_field_map.csv` — 532 rows (518 keys; 288 active key→field mappings, 244 explicit SKIP rows with reasons), same columns as `config/attribute_field_map.csv`.
- `gut_r1_determinations.parquet` — 393,111 rows in the `sample_determinations` column set (one row per sample × field).
- `gut_r1_conflicts.parquet` — 1,515 rows (665 sample×field groups with disagreeing keys; `resolution` column).
- `gut_r1_alternates.parquet` — 69,410 rows collapsed by the one-row-per-(sample, field) rule (lower-ranked keys; useful to the health_condition normalisation leaf).
- `gut_r1_parse_failures.csv` — 552 distinct (key, field, value, reason) parser failures.

## Coverage per field

| field | keys mapped | keys SKIP | rows | samples | share of 437,184 | studies | mean conf |
|---|---|---|---|---|---|---|---|
| age_at_collection_days | 13.0 | 28.0 | 64,909 | 64,909 | 14.85 % | 414 | 0.735 |
| antibiotic_exposure | 37.0 | 28.0 | 10,274 | 10,274 | 2.35 % | 43 | 0.791 |
| bmi | 7.0 | 8.0 | 27,237 | 27,237 | 6.23 % | 141 | 0.895 |
| health_condition_detail | 127.0 | 115.0 | 38,935 | 38,935 | 8.91 % | 309 | 0.896 |
| sex | 11.0 | 2.0 | 95,039 | 95,039 | 21.74 % | 452 | 0.900 |
| subject_id | 39.0 | 34.0 | 120,647 | 120,647 | 27.60 % | 435 | 0.847 |
| timepoint_label | 54.0 | 29.0 | 36,070 | 36,070 | 8.25 % | 179 | 0.850 |

Any field: 168,763 samples (38.6 % of 437,184) in 870 studies (35.5 % of 2,448).

## Value distributions (sanity)

- age_at_collection_days by life stage (from committed days): {'neonate<=28d': 87, 'infant<=3y': 2013, 'child': 4942, 'adolescent': 2172, 'adult': 45520, 'elderly': 10165}
- age parse routes: {'bare_number_years_rule': 52628, 'unit_key': 9171, 'num_unit': 1545, 'numeric': 1464, 'gender_and_age': 101}
- sex: {'female': 48375, 'male': 46664}
- antibiotic_exposure: {'no': 7659, 'yes': 2615}
- bmi: {'count': 27237.0, 'mean': 25.6, 'std': 5.6, 'min': 10.9, '25%': 21.8, '50%': 24.6, '75%': 28.3, 'max': 78.0}

## Top evidence keys per field

- **age_at_collection_days**: host_age (37,287), age (26,057), age_at_collection (725), age_years (201), age_month (110), age_days (104)
- **antibiotic_exposure**: abx_last_month (1,651), antibiotics_past_3_months (1,409), antibiotics (1,041), antibiotics_lastmonth (894), current_antibiotics (645), antibiotic_treatment_during_hospitalization (623)
- **bmi**: host_body_mass_index (19,272), bmi (5,957), body_mass_index (1,028), bmi_t0 (428), baseline_bmi (243), bmi_calulated (216)
- **health_condition_detail**: host_disease (9,403), host_disease_status (3,683), disease (2,445), diagnosis (2,265), gastrointest_disord (2,136), host_phenotype (1,492)
- **sex**: sex (53,389), host_sex (34,384), gender (5,638), arrayexpress_sex (797), gender1 (217), host_other_gender (155)
- **subject_id**: host_subject_id (48,032), gap_subject_id (25,785), subject_id (14,709), subject (6,051), family_subject_id (3,738), participant_id (3,708)
- **timepoint_label**: timepoint (5,789), period (3,179), round (3,154), visit (2,867), time_point (2,712), time (2,007)

## Rules applied

- **Age units.** Bare numbers under `host_age`/`age` take the unit from a sibling unit key on the same sample (`host_age_units`, `host_age_unit`, `age_unit`, `age_units`; 10,932 samples) → confidence 0.9; otherwise the ADULT DEFAULT applies: **bare number = YEARS**, plausibility 0–110 y, confidence 0.7 (`parse_note = bare_number_years_rule`; recorded in the map's `note`). Keys with the unit in their name (`age_years`, `age_months`, `age_month`, `host_age_months`, `age_days`, `age_wk`, `age_weeks`, `age_in_years`) use that unit at 0.9. Text ages ("33 years", "12 Months", "71y", ISO 8601) go through the infant `r1_parsers.parse_age_text`. Ranges/bins ("20-24", ">70", "5 - 17 years", decade bins) and word ages other than newborn are NOT values (rule: ranges are not values) and are logged as failures. `age_at_collection`, `age_at_visit` (unitless, 54–84) use the years rule at 0.7. `gender_and_age` ("Female_44") yields sex + age.
- **sex.** infant `parse_sex` plus Spanish/German tokens (mujer/hombre/w/frau/mann). Coded 1/2 without a legend and "pooled male and female" are failures.
- **bmi.** numeric only, plausible 10–80 kg/m²; categories, z-scores, percentiles and maternal pre-pregnancy BMI are SKIP. `baseline_bmi`/`bmi_t0` at 0.7 (may predate collection).
- **health_condition_detail.** Raw text of disease/diagnosis/status/case-control keys passed through verbatim (≤120 chars) at 0.9 with the key in `evidence_source` (parser `health_text`); disease-specific yes/no keys (`crohns_disease=Y`, `diabetes_mellitus_in_past=no`, `iscontrol=True` …) are emitted as `"<condition from key>: yes|no"` at 0.85 (parser `health_bool_key`; self-diagnosed → 0.6). Trial arms, cohort labels, generic `group`/`status`/`treatment`, disease sub-attributes (duration, extent, activity scores, medication) and outcomes (death, ICU, mortality) are SKIP with reasons. The CODE is assigned by the separate normalisation leaf.
- **antibiotic_exposure.** yes/no from boolean-like values (infant `parse_yesno`), phrases (current/recent/Used/Post Antibiotics/1To3Days → yes; Not_Used/untreated/NoTreatment/Pre Antibiotics/"I have not taken antibiotics in the past year" → no) and drug names (→ yes). Only keys whose own window is current or ≤ 6 months are mapped; 12-month/lifetime windows, coded values without legend, doses, time-since values, maternal/prenatal keys, culture selection agents and `antibiotic_name` (isolate-selection context) are SKIP. `control`, "6 months", "Year" and free-text histories are failures (ambiguous). Trial arm `host_subject_assigned_to_antibiotics_arm` at 0.6.
- **subject_id.** identifier keys pass through after dropping nulls, sex-like values, group words, values equal to the sample accession and values constant across a (study, key) with > 3 samples (206 rows, 5 groups). `anonymized_name`, `donor`, `imu_individual`, `alternativename` at 0.5 (often sample codes). Generic `id`, `identifier`, `family_id` and composites → SKIP.
- **timepoint_label.** visit/timepoint/study-day keys pass through; clock times and calendar dates are dropped; `collection_date`/`collection_timestamp` never mapped.
- **country** not extracted (the registry already normalises geo_loc_name).
- **One row per (sample, field).** When several keys yield the same field: highest confidence, then the key used by the fewest studies (most specific), then key name. Numeric fields conflict when values differ by > 10 %; categorical fields when values differ. Two deterministic refinements: (a) an integer `age_years` value (±1 y resolution) is dropped when the remaining keys agree within 10 % (387 rows, e.g. host_age 0.33 y + age_months 4 vs age_years 0); (b) for antibiotic_exposure a `yes` from any mapped key dominates a `no` from another key (field definition = any antibiotics at/before sampling; curation rule 7) and is committed at 0.7 with the keys listed in `parse_note` (1,109 rows). The remaining 9 groups (19 rows, all age) are committed for NEITHER key and listed in `gut_r1_conflicts.parquet` (e.g. `host_age 11.3` bare vs `age_weeks 11.3`; `age_days 830` vs `age_months 24`).

## Parser failures (distinct values; all logged in gut_r1_parse_failures.csv)

| field | reason | n rows | examples |
|---|---|---|---|
| age_at_collection_days | unparsed | 2,129 | adult ; >70 ; <70 ; >=65 ; 100+ |
| antibiotic_exposure | ambiguous | 501 | control ; 6 months ; Year ; More than 1 week no antibiotics ; 2 |
| bmi | implausible | 435 | 0 ; 0.0 ; 86.1 ; 136 ; 130 |
| antibiotic_exposure | unparsed | 167 | for ear infection ; He was prescribed antibiotics for constant ear infections. He was also prescribe ; Flygyl unk dose (2011-unk; pouchitis) ; A year  |
| bmi | unparsed | 127 | <30 ; UBERON:milk ; M ; F ; NV |
| sex | unparsed | 124 | 2 ; 1 ; not providednot provided ; pooled male and female ; t |
| age_at_collection_days | bare number out of 0-110 years | 66 | 999 ; 489 ; 1094 ; 673 ; 678 |
| age_at_collection_days | range_not_value | 49 | 5 - 17 years ; 26-55 years ; 15-21 days |
| timepoint_label | clock_time | 27 | 14:20:00 ; 18:20:00 ; 15:20:00 ; 20:19:59 ; 17:19:59 |
| health_condition_detail | numeric_only | 14 | 13372 ; 0060041 ; 0050561 ; 1485 |

## LLM use
Utility model (host.llm default), key triage only: 412 keys with ≥ 2 studies not covered by the hand-built map and not matching technical-key patterns, 11 requests × ≤ 40 keys, **89,162 tokens**. 88 keys were proposed for a field; each was checked against its example values — 46 accepted (e.g. `gastrointest_disord` 32 studies, `liver_disord` 10 studies, `config` case/control, `sid`/`pid`/`ptnumber`, `bmtday`), 42 rejected and recorded as SKIP rows with the reason (scores, outcomes, generic `id`, `chem_administration`, `tmp`). No value was classified by the model.

## Deviations and caveats
- Key-level triage covered hand-built regex families over all 4,936 keys plus LLM triage of the ≥ 2-study long tail (412 keys); single-study keys outside the regex families were not reviewed — coverage of `health_condition_detail` on single-study deposits is therefore a lower bound.
- The bare-number = YEARS rule is a documented assumption (confidence 0.7, parse_note `bare_number_years_rule`, 52,628 rows in 365 studies). Two studies have a median bare `host_age` < 3 (PRJNA1401517: median 1, max 2, n = 103; PRJEB44121: 0.51–0.78, n = 26) and may actually be months/decimal years — they are committed at 0.7 and should be re-checked by R2/R3 before the infant filter uses them.
- health_condition_detail keeps one key per sample; 21,299 lower-ranked rows are in `gut_r1_alternates.parquet` rather than lost.
- Studies without any attribute rows (2,448 − 2427 = 21) cannot be covered by R1.
- `is_placeholder` is False for every input row; the infant NULLS vocabulary was applied instead.
- No pushes; nothing written to the pipeline repo. The field map is delivered as an artifact for the owner to commit under `config/packs/`.

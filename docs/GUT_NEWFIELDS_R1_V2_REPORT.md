# R2026.13 / package 1.13.0 — new fields v2, route R1 (diet, smoking_status, medication, stool_consistency_bristol)

Leaf `gut-newfields-r1-v2` (`src/catalog/scopes/newfields_r1_v2.py`), run 2026-09-30 against the 1.12.0 package. Every value in this report is read
from the leaf outputs (`gut_r1_newfields_v2_summary.json`, the determination / map / reject parquet files) or from the proof-run scope-build summary.

## 1. Inputs and join

* Attribute rows: **88,803** BioSample attribute rows (artifact `gut_biosample_attributes_newfields_v2`), 31,342 BioSamples, 172 catalog studies,
  257 distinct normalised keys; 15,833 rows flagged as placeholders by the harvest.
* Sample-key join (`newfields_r1._sample_key_map`: biosample_accession / secondary_sample of the 1.12.0 wide table, run-unit samples via `gut_runs`):
  88,803 of 88,803 rows mapped (31,342 sample keys, 174 studies) — no unmapped rows.
* Vocabularies: `config/vocab/diet.yaml` (14 codes), `smoking.yaml` (4), `medication.yaml` (17). `smoking.yaml` did not parse (unquoted `note:` holding
  `"smoker: yes"`); the note was turned into a block scalar with identical text — no code or match term changed.

## 2. Method (per field)

Every committed row: route `R1`, scope `sample`, `evidence_source = biosample.attribute:<attr_key_norm>`, `evidence_locator` = BioSample accession,
`evidence_quote` = the raw attribute value (≤ 12 words), `determined_by = gut_newfields_r1_v2`, `src_track = gut_all_v1`, `release_added = R2026.13`,
`package_added = 1.13.0`. Placeholders never produce a row. One row per (sample, field) after conflict resolution (confidence, then code specificity for diet,
then key priority); losers with a different value go to `gut_r1_newfields_v2_conflicts.parquet` (82 rows: {'diet': 55, 'smoking_status': 27}).

* **diet** — 22 text-key families (host_diet, diet, special_diet, diet_type, dietary_regime_*, treatment_grp, parent narratives …), 14 boolean
  keys (vegetarian = 1, specialized_diet_* = true) and 4 no-special-diet flags. Deterministic `match_terms` + documented synonyms first (whole-word,
  stem inflections, negation check: "we avoid processed foods" is not western); a hedged value (semi-vegetarian, flexitarian, mostly …) or a narrative of > 8 words is
  deferred; the long tail of DISTINCT (key, value) strings goes to the utility model (claude-haiku-4-5-20251001) which must return the exact span of the raw value that states the
  pattern. Guard: span ⊂ raw value; for a closed code the span must contain a vocabulary match term or a module synonym; `other_diet` / `therapeutic_or_study_diet`
  only for a stated, non-arm span (never control / habitual / baseline / A / B); parent narratives (general_diet, s_specificdiet_*, dietary_restrictions_details_*)
  may yield only closed codes on a ≤ 4-word span or a named diet (kosher, paleo, casein-free …). `omnivore` at 0.9 only when stated (omnivore, non-vegetarian,
  meat consumer); a no-special-diet / no-restriction statement or flag → omnivore at **0.7** with a parse_note. Whole-value abbreviations MIND / Med → 0.7 with a note.
  Numeric arm codes (0/1, A/B, control, habitual, 'other(to be specified)') are rejected, never guessed. `diet_detail` = the raw statement (≤ 120 chars) on every diet row.
* **smoking_status** — keys smoking_status / smoking / smoker / smokingstatus / smoking_history / smoking_frequency / do_you_smoke / smoke / tobacco_use /
  nicotine_consumption. never / former / current from explicit words (0.9); yes/no answers on a smoking key → current / never (0.8); `0`/`1` only on a yes/no-style key
  whose (study, key) value set is exactly {0, 1} → never / current (0.7, note); three-level numeric codes (0/1/2), durations ('20+ years', pack-years),
  'smoked', 'smoking history = yes' and passive exposure stay unknown. Dated windows: an ended range ('10 cigs (1983-1993)') → former 0.8, '-pres' → current.
* **medication** — ';'-joined sorted codes. Sources: (a) free-text list keys (medications, medication, ihmc_medication_code, drug_usage, other_drugs, treatment,
  treatment_type, therapy, treatment_status, treatment_group, etiology_drugs): deterministic drug-name / brand synonyms (documented in `MED_SYNONYMS`), then the
  utility model on the long tail and on lists with unrecognised items — each returned (code, term) kept only when the term occurs verbatim in the raw value and is
  not an antibiotic / antifungal / antiparasitic (`ANTIBIOTIC_RE`; those are `antibiotic_exposure`, never a medication code); (b) 80 per-class yes/no keys
  (ppi_last_month = yes → ppi, laxatives = y → laxative, steroids = 1 → corticosteroid, antiretroviral_treatment = yes → antiretroviral …; windows longer than
  "shortly before sampling" — prior_*, *_day_365, *_at_any_time*, *_brf — excluded; a drug name under a class key yields the class + the named drug's class);
  (c) `no_previous_medication = yes` → none_reported (0.7). Dated IBD histories with an ended window ('ADA 40 mg (3/2015-7/2015)', 'd/c', 'failed therapy',
  'prior …, none current') and bare past dates are rejected; only '-pres' / ongoing statements are kept. `none_reported` only for an explicit no-medication statement
  on a medication key ('treatment: untreated' / 'therapy: none' speak about the disease therapy and are rejected). Per sample the codes of all contributing keys are
  unioned (none_reported dropped when another code exists); the row's evidence is the highest-priority key, the other keys are listed in `parse_note`;
  `medication_detail` = the raw drug text(s) (≤ 160 chars) when any key carried text.
* **stool_consistency_bristol** — keys stool_consistency_bristol_scale / bristol_score / bristol_stool_scale / bristol_stool_chart / bristol_type / bss_stool_type /
  stool_consistency. Integers 1–7 as stated (also '4.0', 'type 4') at 0.9; hard / normal / loose / watery (+ constipated, formed, liquid) → 2 / 4 / 6 / 7 at 0.7 with
  a parse_note; ranges ('type 3-4'), per-subject means ('5.333'), 'grade-N' (another scale) and 'soft' are rejected.

## 3. Coverage (rows committed; 579,252 catalog samples)

| field | rows | samples | studies | share of catalog samples |
|---|---|---|---|---|
| diet | 4168 | 4168 | 42 | 0.0072 |
| diet_detail | 4168 | 4168 | 42 | 0.0072 |
| medication | 3829 | 3829 | 42 | 0.00661 |
| medication_detail | 1849 | 1849 | 26 | 0.00319 |
| smoking_status | 4823 | 4823 | 20 | 0.00833 |
| stool_consistency_bristol | 3037 | 3037 | 11 | 0.00524 |

Confidence tiers per field (rows):

| field_name | 0.7 | 0.75 | 0.8 | 0.85 | 0.9 |
|---|---|---|---|---|---|
| diet | 728 | 14 | 0 | 180 | 3246 |
| diet_detail | 728 | 14 | 0 | 180 | 3246 |
| medication | 10 | 185 | 3 | 307 | 3324 |
| medication_detail | 0 | 185 | 3 | 307 | 1354 |
| smoking_status | 253 | 0 | 1476 | 0 | 3094 |
| stool_consistency_bristol | 61 | 0 | 0 | 0 | 2976 |

Attribute keys behind the rows: 108 (field, key) pairs — the full list is in `gut_r1_newfields_v2_summary.json` → `keys_used` and in the determination
table's `evidence_source`. Top keys (samples / studies):

| field_name | key | samples | studies |
|---|---|---|---|
| diet | host_diet | 2183 | 29 |
| diet | diet | 611 | 6 |
| diet | special_diet | 425 | 1 |
| diet | diet_type | 197 | 1 |
| diet | dietary_regime_biospecimen | 189 | 1 |
| diet | vegetarian | 180 | 1 |
| diet_detail | host_diet | 2183 | 29 |
| diet_detail | diet | 611 | 6 |
| diet_detail | special_diet | 425 | 1 |
| diet_detail | diet_type | 197 | 1 |
| diet_detail | dietary_regime_biospecimen | 189 | 1 |
| diet_detail | vegetarian | 180 | 1 |
| medication | treatment | 782 | 9 |
| medication | treatment_type | 494 | 1 |
| medication | other_medications | 452 | 2 |
| medication | drug_usage | 260 | 2 |
| medication | antiretroviral_treatment | 202 | 1 |
| medication | laxatives | 186 | 3 |
| medication_detail | treatment | 782 | 9 |
| medication_detail | treatment_type | 494 | 1 |
| medication_detail | drug_usage | 132 | 2 |
| medication_detail | medications | 87 | 1 |
| medication_detail | immunotherapy_drug | 72 | 1 |
| medication_detail | immunotherapy | 48 | 1 |
| smoking_status | smoking | 1661 | 7 |
| smoking_status | smoking_status | 1262 | 1 |
| smoking_status | do_you_smoke | 703 | 1 |
| smoking_status | smoking_frequency | 630 | 3 |
| smoking_status | smoker | 338 | 6 |
| smoking_status | nicotine_consumption | 97 | 2 |
| stool_consistency_bristol | bristol_score | 1505 | 3 |
| stool_consistency_bristol | bristol_stool_chart | 687 | 1 |
| stool_consistency_bristol | bristol_stool_scale | 317 | 2 |
| stool_consistency_bristol | stool_consistency_bristol_scale | 265 | 1 |
| stool_consistency_bristol | bss_stool_type | 125 | 1 |
| stool_consistency_bristol | stool_consistency | 88 | 2 |

## 4. Code counts

diet:

| code | samples |
|---|---|
| therapeutic_or_study_diet | 1872 |
| omnivore | 1299 |
| vegan | 285 |
| vegetarian | 267 |
| mediterranean | 164 |
| other_diet | 152 |
| pescatarian | 48 |
| gluten_free | 26 |
| western_or_processed | 25 |
| high_fibre_or_whole_food | 20 |
| low_carbohydrate_or_ketogenic | 10 |

smoking_status:

| code | samples |
|---|---|
| never | 3488 |
| former | 797 |
| current | 538 |

medication (code occurrences across the 3,829 sample lists; 479 samples carry ≥ 2 codes):

| code | occurrences |
|---|---|
| immunosuppressant_or_biologic | 1464 |
| other_medication | 1061 |
| nsaid_or_aspirin | 406 |
| corticosteroid | 339 |
| ppi | 335 |
| antiretroviral | 221 |
| laxative | 219 |
| none_reported | 134 |
| statin | 96 |
| probiotic_or_prebiotic | 45 |
| metformin | 40 |
| antidepressant_or_antipsychotic | 29 |
| antihypertensive | 18 |
| antidiabetic_other | 14 |
| hormonal_contraceptive_or_hrt | 7 |
| chemotherapy | 6 |

stool_consistency_bristol:

| Bristol type | samples |
|---|---|
| 1 | 208 |
| 2 | 398 |
| 3 | 522 |
| 4 | 1264 |
| 5 | 245 |
| 6 | 314 |
| 7 | 86 |

## 5. Normalisation maps (reviewable)

Distinct (key, value) strings by method — `gut_diet_map.parquet`: {'utility_null': 82, 'match_terms': 77, 'utility_rejected': 64, 'reject:arm_or_code': 51, 'reject:placeholder': 37, 'reject:flag_false': 13, 'named_other_diet': 12, 'flag_key': 5, 'utility_open_code': 5, 'no_special_flag': 3, 'reject:special_diet_unspecified': 3, 'no_special_statement': 3, 'utility_match_term': 3, 'abbreviation': 2, 'reject:non_human_diet': 1};
`gut_medication_map.parquet`: {'reject:historical_window': 160, 'reject:dated_window_unclear': 106, 'utility_arm': 102, 'match_terms': 97, 'reject:arm_or_code': 53, 'utility_guarded': 49, 'match_terms+utility_guarded': 44, 'utility_no_code': 26, 'reject:placeholder': 17, 'reject:antibiotic_only': 9, 'match_terms+utility_no_code': 3, 'match_terms+utility_arm': 1};
`gut_smoking_map.parquet`: {'parse_smoking': 58, 'reject:placeholder': 10, 'reject:coded_scale': 8, 'reject:unrecognised': 5, 'reject:duration_only': 4, 'reject:history_yes_ambiguous': 1, 'reject:ambiguous_tense': 1, 'reject:passive_exposure': 1}.

Top diet mappings:

| attr_key_norm | attr_value | code | confidence | method | n_rows |
|---|---|---|---|---|---|
| host_diet | MIND | therapeutic_or_study_diet | 0.7 | abbreviation | 312 |
| host_diet | Omnivore | omnivore | 0.9 | match_terms | 249 |
| host_diet | omnivore | omnivore | 0.9 | match_terms | 188 |
| vegetarian | 1 | vegetarian | 0.85 | flag_key | 180 |
| diet_type | Omnivore | omnivore | 0.9 | match_terms | 177 |
| host_diet | Vegan | vegan | 0.9 | match_terms | 171 |
| diet | SCD | therapeutic_or_study_diet | 0.9 | match_terms | 162 |
| dietary_regime_biospecimen | Omnivorous diet | omnivore | 0.9 | match_terms | 159 |
| diet | Med | mediterranean | 0.7 | abbreviation | 151 |
| specialized_diet_i_do_not_eat_a_specialized_diet | true | omnivore | 0.7 | flag_key | 149 |
| host_diet | EEN | therapeutic_or_study_diet | 0.9 | match_terms | 144 |
| dietary_restrictions_m3_biospecimen | False | omnivore | 0.7 | no_special_flag | 142 |
| host_diet | High-gluten diet | therapeutic_or_study_diet | 0.9 | match_terms | 104 |
| host_diet | Low-gluten diet | therapeutic_or_study_diet | 0.9 | match_terms | 104 |
| special_diet_details | PPD: pulses and plant proteins-enriched diet (surrogating re | therapeutic_or_study_diet | 0.7 | utility_open_code | 85 |
| special_diet_details | PulD: pulses-enriched diet (surrogating red meat proteins) | therapeutic_or_study_diet | 0.9 | match_terms | 84 |
| special_diet | High protein diet 6 Weeks | therapeutic_or_study_diet | 0.9 | match_terms | 77 |
| host_diet | Non_veg | omnivore | 0.9 | match_terms | 75 |
| special_diet | High protein diet 0 Weeks | therapeutic_or_study_diet | 0.9 | match_terms | 74 |
| special_diet | High protein diet 12 Weeks | therapeutic_or_study_diet | 0.9 | match_terms | 73 |
| special_diet | Low protein diet 12 Weeks | therapeutic_or_study_diet | 0.9 | match_terms | 71 |
| host_diet | fasting+DASH | therapeutic_or_study_diet | 0.9 | match_terms | 69 |
| special_diet | Low protein diet 6 Weeks | therapeutic_or_study_diet | 0.9 | match_terms | 67 |
| treatment_grp | Omnivore | omnivore | 0.9 | match_terms | 65 |
| special_diet_yn | 0 | omnivore | 0.7 | no_special_flag | 65 |

Top medication mappings:

| attr_key_norm | attr_value | codes | method | n_rows |
|---|---|---|---|---|
| treatment | anti-PD1 | immunosuppressant_or_biologic | match_terms | 162 |
| treatment | VDZ | immunosuppressant_or_biologic | match_terms | 151 |
| treatment_type | Gilenya | immunosuppressant_or_biologic | match_terms | 138 |
| drug_usage | none | none_reported | match_terms | 128 |
| treatment | IFX | immunosuppressant_or_biologic | match_terms | 107 |
| treatment_type | Tecfidera | immunosuppressant_or_biologic | match_terms | 106 |
| treatment_type | Copaxone | immunosuppressant_or_biologic | match_terms | 99 |
| treatment | UST | immunosuppressant_or_biologic | match_terms | 98 |
| treatment | ADA | immunosuppressant_or_biologic | match_terms | 76 |
| immunotherapy_drug | Pembrolizumab | immunosuppressant_or_biologic | match_terms | 69 |
| treatment_type | Rebif | immunosuppressant_or_biologic | match_terms | 68 |
| treatment | anti-PD-L1 | immunosuppressant_or_biologic | match_terms | 51 |
| treatment_type | Tysabri | immunosuppressant_or_biologic | match_terms | 43 |
| medications | prenatal vitamins | other_medication | utility_guarded | 33 |
| treatment_type | Avonex | immunosuppressant_or_biologic | match_terms | 28 |
| treatment | other ICB | immunosuppressant_or_biologic | match_terms | 25 |
| treatment | probiotic | probiotic_or_prebiotic | match_terms | 24 |
| immunotherapy | PD1 | immunosuppressant_or_biologic | match_terms | 24 |
| other_drugs | mycophenolate mofetil | immunosuppressant_or_biologic | match_terms | 24 |
| immunotherapy_drug | Nivolumab | immunosuppressant_or_biologic | match_terms | 23 |
| immunotherapy | CTLA4/PD1 | immunosuppressant_or_biologic | match_terms+utility_arm | 23 |
| steroid_used | Prednisone | corticosteroid | match_terms | 20 |
| treatment | Anti-PD1 | immunosuppressant_or_biologic | match_terms | 20 |
| treatment | MTX | immunosuppressant_or_biologic | match_terms | 17 |
| drug_usage | protein-pump inhibitor | ppi | match_terms | 16 |

Top smoking mappings:

| attr_key_norm | attr_value | code | confidence | n_rows |
|---|---|---|---|---|
| smoking_status | never | never | 0.9 | 876 |
| smoking | Ex smoker | former | 0.9 | 754 |
| do_you_smoke | N | never | 0.8 | 678 |
| smoking | Never smoked | never | 0.9 | 616 |
| smoker | no | never | 0.8 | 565 |
| smoking_frequency | never | never | 0.9 | 435 |
| smoking | Smoker | current | 0.9 | 386 |
| smoking_status | former | former | 0.9 | 386 |
| smoking | No | never | 0.8 | 250 |
| smoking_frequency | Never | never | 0.9 | 197 |
| smoking | 0 | never | 0.7 | 159 |
| smoking | N | never | 0.8 | 152 |
| smoker | ciggaretes | current | 0.9 | 82 |
| smoking_frequency | everyday | current | 0.9 | 69 |
| smoking | never | never | 0.9 | 68 |
| nicotine_consumption | No | never | 0.8 | 67 |
| smoker | yes | current | 0.8 | 59 |
| smoker | Nonsmoker | never | 0.9 | 54 |
| smoking | Smoker occasionally | current | 0.9 | 50 |
| tobacco_use | 0 | never | 0.7 | 49 |

## 6. Rejects (`gut_r1_newfields_v2_rejects.parquet`, 9,457 attribute rows; placeholders and negative flags are not listed)

| field_name | reason | rows | samples | studies | distinct_values |
|---|---|---|---|---|---|
| diet | arm_or_code | 1578 | 1549 | 18 | 49 |
| diet | utility_null | 233 | 215 | 3 | 82 |
| diet | utility_rejected | 115 | 102 | 4 | 63 |
| diet | special_diet_unspecified | 64 | 62 | 2 | 2 |
| diet | non_human_diet | 8 | 8 | 1 | 1 |
| medication | arm_or_code | 4700 | 4526 | 31 | 45 |
| medication | utility_arm | 403 | 403 | 13 | 102 |
| medication | antibiotic_only | 101 | 101 | 5 | 9 |
| medication | utility_no_code | 68 | 68 | 12 | 24 |
| medication | historical_window | 24 | 24 | 1 | 24 |
| medication | none_on_treatment_key | 6 | 6 | 1 | 1 |
| smoking_status | coded_scale | 931 | 931 | 3 | 3 |
| smoking_status | duration_only | 30 | 30 | 2 | 4 |
| smoking_status | history_yes_ambiguous | 23 | 23 | 1 | 1 |
| smoking_status | ambiguous_tense | 11 | 11 | 1 | 1 |
| smoking_status | unrecognised | 5 | 5 | 1 | 5 |
| smoking_status | passive_exposure | 2 | 2 | 1 | 1 |
| stool_consistency_bristol | unknown_scale | 710 | 710 | 1 | 4 |
| stool_consistency_bristol | non_integer_mean | 178 | 178 | 3 | 95 |
| stool_consistency_bristol | range | 176 | 176 | 1 | 3 |
| stool_consistency_bristol | textual_unmapped | 91 | 91 | 1 | 1 |

Reading the table: `arm_or_code` = study-arm labels, numeric codes and deny-listed words (control, habitual, FMT, placebo, 0/1 …); `utility_arm` /
`utility_null` = the model judged the value a non-medication / non-diet (BRF, isotype, PBS, food logs without a pattern); `utility_rejected` = a model proposal that
failed the substring / match-term / hedge guard (kept unknown); `coded_scale` = smoking_history / smokingstatus 0/1/2 codes with no key; `unknown_scale` =
`stool_consistency: grade-1..4` (not Bristol); `non_integer_mean` = per-subject Bristol means; `historical_window` / `dated_window_unclear` = dated medication
histories (see §2). None of these rows is inferred.

## 7. Utility-model usage

Model role `utility` → `screen` (Haiku class; `claude-haiku-4-5-20251001`), no temperature sent. Final leaf pass: 12 calls,
66,329 input + 25,156 output tokens, 0 cache reads; one extra single-item call (4,077 + 71) for a value
that became model-eligible after the last guard change. An earlier exploratory pass (superseded guards) used 14 calls,
75,472 + 27,754 tokens. Session total 198,859 uncached tokens (ceiling 1.5 M). The maps are reusable
(`--diet-map` / `--medication-map`) so a re-run of the leaf needs no model call.

## 8. Scope build proof-run (1.12.0 package + v2 rows → 1.13.0-shaped tables)

`catalog.scopes.build_gut_scope` was extended: `--r1-newfields-v2` input; pack types `vocab_list` (medication: every code of the ';'-list validated against the
vocabulary, invalid codes dropped, row dropped when none remain) and `int` with `range` (stool_consistency_bristol: integer within [1, 7]); the wide table gets the
four new columns plus diet_detail / medication_detail, each with `__confidence` / `__route`; stool_consistency_bristol is a nullable `Int64` column; the summary
reports diet / smoking_status / medication_codes / stool_consistency_bristol counts. Run with `RELEASE_ID=R2026.13 VERSION=1.13.0` overrides against the 1.12.0
package (studies input = package gut_studies without the built `cov_*` columns; `--r1` = the 1.12.0 gut_sample_determinations; no registry_runs → gut_runs not rebuilt):

* 2,837 studies, 579,252 samples, 3,158,581 determinations (1.12.0: 3,136,707; +21,874 = the v2 rows), 1,391 conflicts.
* vocab / range validation dropped: {'health_condition': 0, 'lifestyle': 0, 'diet': 0, 'smoking_status': 0, 'medication': 0, 'medication__codes': 0, 'stool_consistency_bristol': 0}.
* Wide-table coverage of the new columns: {'diet': 0.0072, 'diet_detail': 0.0072, 'smoking_status': 0.0083, 'medication': 0.0066, 'medication_detail': 0.0032, 'stool_consistency_bristol': 0.0052};
  unchanged for the 1.12.0 fields (country 527,707; collection_date 340,455; lifestyle 10,658; health_condition 217,169 non-null — identical to 1.12.0).
* All v2 rows carry release_added R2026.13 / package_added 1.13.0; earlier rows keep their release columns through `carry_release_columns`.

## 9. Tests, Makefile, docs

* `tests/test_newfields_r1_v2.py`: 287 collected cases — diet 44 accept + 25 reject + 6 deferred + guard cases; smoking 36 accept + 26 reject; medication 52 accept + 28 reject + 6 deferred + flag / guard cases; Bristol 28 accept + 26 reject; determination-row schema; term / negation matcher; build_gut_scope `pack_fields`,
  `clean_vocab_list`, `clean_int`, `validate_vocab_fields`. `tests/test_newfields_r1.py` updated for the extended pack (assertions that enumerated the 1.12.0
  vocab fields; module-level `PACK_FIELDS` extended). Both files: 478 passed.
* Makefile: target `gut-newfields-r1-v2` (input `GUT_ATTRIBUTES_V2`, output `GUT_R1_NEWFIELDS_V2`, `--diet-map` / `--medication-map` / `NO_LLM` switches); `gut-build`
  passes `--r1-newfields-v2 "$(GUT_R1_NEWFIELDS_V2)"`.
* Config: no version bump; `config/vocab/smoking.yaml` YAML fix only (see §1).

## 10. Caveats for the owner

* Coverage is small (≤ 0.9 % of catalog samples per field) because only 172 of 2,837 studies deposit any such attribute; routes R2–R4 are the next step (the
  pack allows them for diet / smoking / medication; Bristol is R1/R2 only).
* `therapeutic_or_study_diet` dominates diet (1,872) — diet-intervention trials label arms by diet (SCD, EEN, high/low protein, MIND, low/high-gluten);
  the arm name is a stated diet at sampling but not a habitual pattern — filter by `diet__confidence` / `diet_detail` when a habitual pattern is needed.
* `immunosuppressant_or_biologic` (1,464) is mostly `treatment` / `treatment_type` arm labels naming the drug (VDZ, IFX, UST, ADA, anti-PD1, MS
  disease-modifying drugs) — a named drug arm is medication taken, but the timing relative to sampling comes from the study design, not the attribute.
* MIND (312 samples) and Med (151) were read as abbreviations at 0.7 (MIND → therapeutic_or_study_diet, Med → mediterranean); `Fiber` (62) and `Fermented` (64)
  are the two arms of a fermented-food / high-fibre intervention and were coded from the model's guarded proposal / the named-diet list (therapeutic_or_study_diet / other_diet).
* Aminosalicylates (mesalamine, sulfasalazine …) are deliberately not immunosuppressant synonyms; they fall to `other_medication` via the model.

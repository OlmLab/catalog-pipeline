# gut_all value normalisation — health_condition and antibiotic_exposure

Scope: `gut_all` curated scope (config/packs/gut.yaml @ microbiome_repo-pipeline 6568731). Inputs: `gut_condition_values.parquet`
(3,719 distinct (attr_key_norm, attr_value) pairs, 106,694 sample-attribute rows) and
`gut_treatment_values.parquet` (1,784 pairs, 44,512 sample-attribute rows). Vocabulary: `config/vocab/health_conditions.yaml`
(29 codes; the 4 `legacy_infant` codes were excluded from every rule and from the model's enum — 0 assigned).
All counts below are pair counts or **sample-attribute-row weights** (`n_samples` of the pair); a sample carrying several
condition keys is counted once per key, so weights are not distinct samples.

## 1. health_condition — `gut_health_condition_map.parquet` (3,719 rows)

Columns: attr_key_norm, attr_value, n_samples, n_studies, health_condition, confidence, method (rule|llm), basis (≤ 12 words), rule_id.

* Coded (code ≠ unknown): **1,615 pairs / 50,593 sample-rows (47.4 % by weight)**.
* unknown: 2,104 pairs / 56,101 sample-rows (52.6 % by weight). Of these, 9,316 rows are the literal
  placeholder `Not supplied` (V0), 11,904 rows sit under keys that are not condition fields (ages at diagnosis, durations, scores,
  cohort ids, demographics — K1) and 17,489 rows are negatives of a single named condition (`crohns_disease = N`, `is_tumor = No`,
  `diabetes = no` — K2), which the vocabulary note says must stay `unknown`, not `healthy_control`.
* Resolved by rule: 2,190 pairs / 77,572 rows (72.7 %); by model: 1,529 pairs / 29,122 rows (27.3 %).

### Code distribution (weighted by sample-rows)

| code | sample-rows | share | pairs |
|---|---:|---:|---:|
| unknown | 56,101 | 52.6 % | 2,104 |
| healthy_control | 9,713 | 9.1 % | 221 |
| other_cancer | 8,994 | 8.4 % | 474 |
| intervention_cohort | 5,344 | 5.0 % | 105 |
| crohns_disease | 4,590 | 4.3 % | 126 |
| other_disease | 3,516 | 3.3 % | 86 |
| ulcerative_colitis | 2,434 | 2.3 % | 172 |
| neurological_psychiatric | 2,097 | 2.0 % | 67 |
| other_infection | 1,974 | 1.9 % | 53 |
| autoimmune_inflammatory | 1,962 | 1.8 % | 46 |
| gi_infection_or_diarrhoea | 1,709 | 1.6 % | 48 |
| liver_disease | 1,593 | 1.5 % | 24 |
| ibd_unspecified | 946 | 0.9 % | 45 |
| allergy_or_atopy | 891 | 0.8 % | 13 |
| transplant_or_immunocompromised | 889 | 0.8 % | 8 |
| colorectal_cancer | 792 | 0.7 % | 30 |
| type2_diabetes | 761 | 0.7 % | 24 |
| kidney_disease | 543 | 0.5 % | 2 |
| ibs | 487 | 0.5 % | 6 |
| cardiometabolic_other | 457 | 0.4 % | 23 |
| colorectal_adenoma | 416 | 0.4 % | 13 |
| type1_diabetes | 241 | 0.2 % | 8 |
| obesity | 139 | 0.1 % | 9 |
| pregnancy_postpartum | 54 | 0.1 % | 8 |
| malnutrition | 51 | 0.0 % | 4 |

### Confidence distribution (sample-rows)

| confidence | pairs | sample-rows |
|---|---:|---:|
| (-0.01, 0.0] | 1,862 | 24,106 |
| (0.0, 0.5] | 249 | 6,908 |
| (0.5, 0.7] | 527 | 9,785 |
| (0.7, 0.85] | 420 | 15,698 |
| (0.85, 1.0] | 661 | 50,197 |

### Deterministic rules (first pass; `rule_id` in the table)

| rule_id | pairs | sample-rows |
|---|---:|---:|
| model (llm) | 1,529 | 29,122 |
| V1_term | 722 | 23,606 |
| K2_negative_for_key | 92 | 17,489 |
| K1_key_not_condition | 1,164 | 11,904 |
| V0_null | 3 | 9,316 |
| V2_healthy_control | 81 | 8,419 |
| K2_positive_for_key | 58 | 2,086 |
| V6_ambiguous_acronym | 6 | 804 |
| V3_intervention | 8 | 747 |
| P5_term_fix | 16 | 533 |
| V4_tissue_inflammation | 6 | 506 |
| P6_activity_key_unnamed | 10 | 500 |
| K3_any_disease_no | 2 | 417 |
| V5_self_rated_health | 2 | 380 |
| P1_negated_value | 6 | 219 |
| P7_ontology_id_from_memory | 4 | 177 |
| P2_risk_group_not_disease | 3 | 156 |
| P3_ambiguous_polarity | 2 | 130 |
| P8_exposure_key_no_disease | 4 | 101 |
| P4_ambiguous_code | 1 | 82 |

Rule definitions (`norm_rules.py`, shipped alongside):
* **V0_null** — placeholder values (`Not supplied`, `missing`, `NA`, `none`, `unknown`, `-`, …) → unknown, confidence 1.0.
* **K1_key_not_condition** — key regex for numeric/administrative keys (`age_at_diagnosis`, `disease_duration`, `tumor_vol`,
  `sibdq`, `*_species`, `fermentation_condition`, `marital_status`, `smoking_*`, `ifsac_category`, `insdc_status`, `*_rf`, `msstatus`, …)
  → unknown, confidence 0. Note `cohort` is deliberately NOT in this list: it carries `Leukemia`, `healthy`, `United States HCT`.
* **K2_positive_for_key / K2_negative_for_key** — the key's own text is run through the same term matcher (`crohns_disease` →
  crohns_disease, `hiv_status` → other_infection, `covid_chronic_conditions_asthma…` → allergy_or_atopy, `diabet*` →
  type2_diabetes at 0.6 because type is unspecified, `*_disease/_disorder/_condition` → other_disease). Affirmative values
  (y/yes/true/positive/`Diagnosed by a medical professional`/case) → the key's code (0.85; 0.6 for unspecified diabetes and
  generic other_disease; 0.5 when the key is a medication or carriage key). Negative values (n/no/false/negative/`I do not have
  this condition`) → unknown 0.9. Bare `0`/`1` are only read as booleans when the key says `_yn`/`yes_no`; activity/severity/
  extent/subtype/stage keys are excluded from K2 and go to the model.
* **K3_any_disease_no** — `any_diagnosed_disease_yes_no = NO` → healthy_control 0.8 (the only negative that means "no disease").
* **V1_term** — value matched against the vocabulary `match_terms` extended with the acronyms and spellings seen in the data
  (word terms case-insensitive; acronyms whole-token, case-sensitive, not followed by digits so `CD8`, `CD000175` do not match
  Crohn's). Two tiers: specific codes (UC, CD, IBS, CRC, adenoma, T1D/T2D, liver, kidney, GI infection, autoimmune, neuro,
  allergy, malnutrition, pregnancy, obesity, cardiometabolic, transplant) win over generic ones (ibd_unspecified, other_cancer,
  other_infection). Exactly one specific match → 0.9 (0.7 when the value lists several conditions); one generic match → 0.85;
  two different specific matches, or any negation token (`non-`, `no`, `without`, `negative`, `free`) → model.
  NAFLD/NASH/MASLD follow the vocabulary (cardiometabolic_other), not the model's preference for liver_disease.
* **V2_healthy_control** — value is essentially the token healthy/control/normal/HC/CTR with at most one qualifier
  (`Population Control`, `Healthy control`, `Elderly_control`) and the key is not a treatment/arm/experimental/storage key →
  0.9 (healthy) / 0.8 (control). `negative control`, `ExposedControl`, `Control - No treatment` go to the model.
* **V3_intervention** — value is exactly placebo / FMT / pre-FMT / post-FMT / probiotic / intervention → intervention_cohort 0.85.
* **V6_ambiguous_acronym** — bare `PD` → neurological_psychiatric at 0.6 (Parkinson's assumed); under ibd/pouch/dialysis/
  response keys → unknown 0.3 (`diagnosis_by_ibd_type = PD` is perianal disease, not Parkinson's).
* **V4/V5/P1–P8** — curator overrides applied on top of model output after review of the two highest-weight pages:
  self-rated health → unknown; inflamed/non-inflamed tissue state → other_disease 0.5 / unknown; risk-group keys → unknown;
  DOID codes without label → unknown (Rule 4: no identifiers from memory); negated single-disease values the model had coded
  as a disease → unknown 0.5; term fixes (gastritis, fibromyalgia, Lynch syndrome, SCA, B12 deficiency, phlegmonous);
  `antibiotic_exposure_cohort` → unknown; `endoscopic/histologic_disease_activity` → other_disease 0.5.

### Model pass

Utility model (host.llm default), batches of 40 pairs, forced tool call with `code` constrained to the 25 non-legacy codes,
`confidence` 0–1 and `basis`. The prompt encodes the key-semantics rules above (binary polarity, negation ≠ healthy,
disease-specific index keys imply the disease at ≤ 0.7, generic `status/group/cohort` codes → unknown 0). 1,404 pairs were sent
(36 batches); every id came back (0 missing, 0 re-runs); 0 out-of-enum codes; bases trimmed to 12 words.

**Audit.** The 1,086 rule-coded, non-unknown pairs were also sent to the model blind. Agreement: 81.0 % of pairs,
82.8 % of sample-rows (206 disagreements, all listed in `gut_health_condition_rule_vs_model_disagreements.csv`;
rule verdicts were kept). The disagreements are dominated by (a) the model refusing `Control` → healthy_control (unknown 0.4)
where the vocabulary lists `control` as a match term, (b) NAFLD → liver_disease vs the vocabulary's cardiometabolic_other,
(c) ICD-10 `Malignant neoplasm of colon/rectum` which the first rule version had left in other_cancer (fixed: now
colorectal_cancer), and (d) `CD8`/`CD000175` false acronym hits (fixed). Top disagreements after the fixes:

| key | value | sample-rows | rule | model |
|---|---|---:|---|---|
| `case_status` | `PD` | 491 | neurological_psychiatric | unknown |
| `host_disease` | `Control` | 478 | healthy_control | unknown |
| `group` | `Control` | 402 | healthy_control | unknown |
| `group` | `PBC Control` | 278 | healthy_control | unknown |
| `group` | `PSC Control` | 245 | healthy_control | unknown |
| `case_status` | `Control` | 234 | healthy_control | unknown |
| `host_disease` | `control` | 216 | healthy_control | unknown |
| `disease_state` | `Control` | 174 | healthy_control | unknown |
| `cohort` | `Controls` | 165 | healthy_control | unknown |
| `disease_course` | `Control` | 154 | healthy_control | unknown |

### Ambiguous-key examples (why `unknown` is large)

| key | value | sample-rows | code | conf | rule |
|---|---|---:|---|---:|---|
| `is_tumor` | `No` | 1,304 | unknown | 0.9 | K2_negative_for_key |
| `cohort` | `PRISM` | 879 | unknown | 0.0 | llm |
| `cohort` | `Cohort 1` | 708 | unknown | 0.0 | llm |
| `crohns_disease` | `N` | 700 | unknown | 0.9 | K2_negative_for_key |
| `celiac_disease` | `N` | 699 | unknown | 0.9 | K2_negative_for_key |
| `gi_cancer_past_3_months` | `N` | 683 | unknown | 0.9 | K2_negative_for_key |
| `ibd` | `N` | 681 | unknown | 0.9 | K2_negative_for_key |
| `cohort` | `Cohort 3` | 642 | unknown | 0.0 | llm |
| `diabetes_med` | `N` | 599 | unknown | 0.9 | K2_negative_for_key |
| `cohort` | `Cohort 2` | 569 | unknown | 0.0 | llm |
| `intestinal_disease` | `N` | 514 | unknown | 0.9 | K2_negative_for_key |
| `case_status` | `PD` | 491 | neurological_psychiatric | 0.6 | V6_ambiguous_acronym |
| `diabetes` | `no` | 480 | unknown | 0.9 | K2_negative_for_key |
| `group` | `A` | 466 | unknown | 0.0 | llm |

Open ambiguities for the curator: `case_status = PD` (491 rows, coded Parkinson's at 0.6); unspecified `diabetes = yes`
(coded type2_diabetes at 0.6); `health_state = Yes/NO` (130 rows, polarity unknown); `colorectal_adenoma_status = co` (82 rows,
probably control); `background_disease = NOD/BALB/B6` are mouse strains inside a "human gut" deposit (unknown).

## 2. antibiotic_exposure — `gut_antibiotic_map.parquet` (456 rows)

Key selection: kept keys matching `antibio|abx|antimicrob|<antibiotic stems>` (69 keys) plus generic treatment keys whose
value names an antibiotic (`treatment_group = Vancomycin_125mg_po_qid`, `drug_usage = antibiotic`, `fistula_treatment = Antibiotic`);
dropped keys about antibiotic allergy or antibiotics in animal products, and antiretroviral / antiparasitic / anti-PD1 /
anti-inflammatory keys. 1,328 of 1,784 input pairs (24,973 sample-rows) were dropped as generic
treatment pairs (`treatment`, `biologic_therapy`, `subsequent_response_therapy`, `days_on_treatment`, …).

* yes: 205 pairs / 4,539 rows; no: 58 pairs / 12,551 rows; unknown: 193 pairs / 2,449 rows.
* Coded (≠ unknown): **263 pairs / 17,090 rows (87.5 % by weight)**.
* Rule: 392 pairs / 19,265 rows; model: 64 pairs / 274 rows (4 batches, 137 pairs sent, 0 missing).

| rule_id | pairs | sample-rows |
|---|---:|---:|
| A4_negative | 44 | 11,200 |
| A3_affirmative | 42 | 2,340 |
| A2_value_names_antibiotic | 129 | 1,520 |
| A9_uncoded_number | 64 | 1,051 |
| A4_control_arm | 2 | 943 |
| A1_maternal_key | 20 | 556 |
| A5_window_flag_negative | 3 | 495 |
| A6_recent_window | 6 | 372 |
| model (llm) | 64 | 274 |
| A7_old_window | 6 | 250 |
| B2_pre_course_sample | 1 | 150 |
| B1_risk_category | 2 | 124 |
| B5_free_text_history | 61 | 108 |
| B3_exposure_cohort_label | 3 | 93 |
| A8_mid_window | 2 | 38 |
| A0_null | 1 | 13 |
| B4_dated_regimen | 6 | 12 |

Rules (`abx_rules.py`): A0 placeholder → unknown; **A1** maternal/prenatal/intrapartum/caesarean keys → unknown 0.3 (the
mother's exposure, subject unclear; infant rows come from the infant tables anyway); **A2** value names an antibiotic or class
(80-name list) → yes 0.85, unless dated (`Cipro 500 mg (10/2016)` → B4 unknown 0.5, sampling date unknown); **A3** affirmative
(y/yes/true/1/positive/used/current/ABX+) → yes 0.9, 0.85 when the key's window is 3–6 months, 0.7 when it is 12 months or
"history" (the pack accepts the source's own window); **A4** negative (n/no/false/0/never/none/not_used/untreated/`I have not
taken antibiotics…`) → no 0.9; `control` under an antibiotic-treatment key → no 0.6; **A5** `0` under window-specific sub-flags
(`anyantimicrobials_15to30days_rf`) → unknown 0.3; **A6** last course ≤ 1 month (`one week`, `1To3Days`) → yes 0.8;
**A7** last course > 3 months / `1y+` → no 0.6 with the window in `basis`; **A8** 1–3 months → unknown 0.5; **A9** numbers whose
coding is not stated (`abx_code2 = 3`, `s_antibiotics_v2 = 2`, `days_since_last_abx = -79`, `minimum_time_since_antibiotics = 3`)
→ unknown 0 — a key whose values include numbers other than 0/1 is treated as a coded scale for all its values. Post-model
overrides: B1 `pre_infusion_abx_risk` (risk category) → unknown; B2 `Pre Antibiotics` (sample before the course) → no 0.7;
B3 exposure-cohort labels capped at 0.7; B5 free-text parent-questionnaire `antibiotic_history` (61 pairs, 108 rows) → unknown 0.3
unless the text is an explicit never (infant-curation-rules Rule 6: respondent history is not exposure at sampling).

## 3. Future-fields inventory — `gut_future_fields_inventory.csv`

Built from `gut_attributes_nonInfant.parquet` (9.41 M non-infant gut attribute rows, placeholder rows excluded), key regexes per
future field; one row per key with n_samples (distinct sample_acc), n_studies, n_distinct_values and the six most frequent values.
Sums below add keys together, so a sample with two diet keys counts twice.

| future_field | keys | sample-rows (sum over keys) | studies (sum over keys) |
|---|---:|---:|---:|
| diet | 182 | 37,056 | 232 |
| medication_metformin | 6 | 1,364 | 10 |
| medication_ppi | 18 | 6,900 | 22 |
| medication_statin | 4 | 1,061 | 5 |
| smoking | 14 | 6,987 | 31 |
| stool_consistency_bristol | 8 | 4,252 | 14 |

Highest-weight keys: diet — `host_diet` (3,310 samples / 35 studies: Control, Habitual, MIND, Omnivore …), `diet` (877 / 9: SCD,
Med, omnivour …), per-food gram/day columns from one 900-sample study; smoking — `smoking` (1,707 / 7: Ex smoker, Never smoked,
Smoker), `smoking_status` (1,262), `smoker` (813 / 7), `smoking_history` (763, coded 0/1/2); PPI — `ppi_last_month` (1,651),
`ppi_day_365` (1,364), `indigestion_drugs` (696), `omeprazol_freq` (547); metformin — `diabetes_med` (698), `metformin` (264 / 3),
`antidiabetics` (97 / 2); statins — `cholesterol_med` (701), `statins` (167), `statines` (97); stool — `bristol_score`
(1,558 / 3), `stool_consistency` (1,012 / 3, `Grade-1…3`, soft), `bristol_stool_chart` (687), `bristol_stool_scale` (493 / 3).
Diet is the only field with enough breadth for a vocabulary (182 keys, 232 study-key combinations); stool consistency is
already numeric Bristol 1–7 in three of the four main keys.

## 4. Token usage

host.llm utility model only (no reasoning-model calls): 479,401 input + 123,391 output = **602,792 tokens**
(condition pass 255,943 + 65,121; audit 197,555 + 51,025; antibiotic pass 25,903 + 7,245). Per-frame ceiling 2.0 M; 1.6 M soft cap respected.

## 5. Deviations and caveats

* The pair maps were expanded into determination rows (section 6) with a per-sample precedence rule chosen here (specific >
  generic > healthy_control, then confidence); that precedence has not been reviewed by the owner.
* `n_samples` weights are sample-attribute rows, not distinct samples (a sample with 30 `covid_chronic_conditions_*` keys is
  counted 30 times in `unknown`).
* Rule verdicts were kept where the audit model disagreed; the 206 disagreements are shipped for curator review, not resolved.
* Curator overrides (V4/V5, P1–P8, B1–B5) were derived from reviewing the ~150 highest-weight model rows; lower-weight model rows
  (≤ 20 sample-rows) were not individually reviewed.
* Unspecified `diabetes` keys are coded type2_diabetes at 0.6; the vocabulary has no diabetes-unspecified code.
* The future-fields inventory uses regex key selection and reports non-infant gut attributes only.

## 6. Expansion into determination rows — `gut_condition_abx_determinations.parquet` (51,707 rows)

The two maps were joined back onto `gut_attributes_nonInfant.parquet` on (attr_key_norm, attr_value) and reduced to one row per
sample and field, using the pack's `determination_schema` columns (route R1, scope `sample`, evidence_source `biosample_attr`,
evidence_locator = the attribute key, evidence_quote = the attribute value, determined_by `r1_attr+det_norm` (rule) or
`r1_attr+haiku_norm` (model), parse_note = rule_id + basis, src_track `gut_all_v1`, release_added R2026.7, package_added 1.8.0,
release_retired null). `unknown` pairs emit no row (no evidence to commit).

* health_condition: 40,035 samples in 317 studies. 6,568 samples carried more than one coded pair and
  2,617 of them carried different codes; precedence = specific disease code > generic code (other_*, ibd_unspecified,
  intervention_cohort) > healthy_control, then higher pair confidence. Distribution: healthy_control 8,422, intervention_cohort 5,146, other_cancer 5,125, crohns_disease 3,461, other_disease 2,307, ulcerative_colitis 2,083, neurological_psychiatric 1,821, autoimmune_inflammatory 1,750, other_infection 1,721, gi_infection_or_diarrhoea 1,668, liver_disease 1,464, allergy_or_atopy 891, colorectal_cancer 570, kidney_disease 543, ibs 487, type2_diabetes 483, cardiometabolic_other 457, colorectal_adenoma 416, ibd_unspecified 412, transplant_or_immunocompromised 382, type1_diabetes 186, obesity 138, pregnancy_postpartum 54, malnutrition 48.
* antibiotic_exposure: 11,672 samples in 51 studies (2,613 yes, 9,059 no);
  4,453 samples had several antibiotic keys and 1,291 had a yes/no conflict — resolved by the higher pair confidence, which
  favours the shorter-window key (`abx_last_month = No` 0.9 over `abx_day_365 = Y` 0.7), matching the pack definition.
* Infant-catalog samples are not in this table (non-infant attribute table only); the curated infant rows win by the pack rule.

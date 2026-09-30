# DQ_HEALTH_LABELS_REPORT — PRJNA50637 (pouch cohort) and PRJNA46337 (NEC cohort)

Wave: R2026.13 / package 1.13.0 preparation. Inputs: package 1.12.0 (gut_sample_metadata_wide, gut_sample_determinations,
registry_biosamples, registry_study_papers), NCBI BioSample XML fetched via eutils for every sample of both studies
(102 + 827 records), Europe PMC search on the accessions read from those records (dbGaP phs000262 / phs000247, PRJNA50637,
SRP002427, PRJNA46337) and Europe PMC full text / abstracts of the hits. Rubric model: 9 requests
(53,948 uncached input + 9,226 output tokens; 43,992 cache-read tokens), used only to map
free text to structured answers with verbatim quotes; every quote was checked as an exact substring of the text.

Output: `dq_corrections_health_labels.parquet` — 1327 rows, 495 corrections (action retire/recode), 832 keep rows
(existing values confirmed and re-anchored to route R1 archive attributes).

## 1. PRJNA50637 — "The Role of the Gut Microbiota in Ulcerative Colitis" (dbGaP phs000262, SRP002427)

**What the evidence says**
* BioSample attributes (all 102 samples, 22 gap_subject_id values): `study_disease=Pouchitis`, `isolation_source=Pouch`,
  `histological_type` luminal aspirate (99) / Brush (3), `is_tumor=Yes` (102), `subject_is_affected=Yes` (102),
  `study_design=Prospective Longitudinal Cohort`, `molecular_data_type` Metagenome (NGS) 99 / 16s rRNA (NGS) 3.
* The catalog's `other_cancer` was minted from `is_tumor=Yes` (determination evidence_locator `is_tumor`, quote `Yes`).
  `is_tumor` is a dbGaP boilerplate field and is identical on every sample; the auto-generated BioSample titles
  ("Pouchitis tumor DNA sample …") derive from it. No attribute and no linked paper states a malignancy.
* Europe PMC hits for phs000262: PMC5111406 (mBio 2016, "Patient-Specific Bacteroides Genome Variants in Pouchitis",
  primary data: 22 patients, University of Chicago, 2-year longitudinal; quote "confirmed diagnosis of ulcerative colitis (UC)",
  §Patient clinical history; "10 patients never developed pouch inflammation", §Patient sampling), PMC5902703 (2018, reanalysis
  of 17 stool samples from phs000262), PMC10865816 (2024, isolate from an ileal pouch of a UC patient; cites phs000262).
  Registry-linked PMC10761161 (2024) is a reanalysis and does not describe the cohort; PMC4269443 / PMC3439730 cite SRP002427 among IBD datasets.
* No statement that any study patient had familial adenomatous polyposis was found: the only FAP/polyposis mentions in the four full texts are 2 in PMC5111406, both inside a reference citation (rubric-model check), none in the other three.

**Decision**
* health_condition: recode `other_cancer` -> `ulcerative_colitis` on all 102 samples (route R3 cohort default from PMC5111406,
  confidence 0.7 per the R3 cap; corroborated by R1 `study_name` "The Role of the Gut Microbiota in Ulcerative Colitis").
  No pouchitis code exists in health_conditions.yaml; `ulcerative_colitis` is the closest gastrointestinal code and the
  underlying diagnosis of every patient. `colorectal_adenoma` is not applicable (no FAP statement). `other_cancer` is kept nowhere.
* health_condition_detail: keep `Pouchitis` (submitter text, 102 keep rows) — caveat: the value is study-wide while the paper
  says 10 of 22 patients never developed pouchitis; the paper's Table S1 uses numeric sample names that cannot be joined to the
  dbGaP subject ids (0 of 22 `UC######` ids found in the supplement), so per-subject pouchitis status is unresolved (owner question 2).

**Counts**: 102 recode (health_condition), 102 keep (health_condition_detail).

**Observations outside this task's mandate** (not corrected here): body_site_code is `unknown_site` for all 102 samples although
`isolation_source=Pouch` (ileal pouch); 3 samples are `molecular_data_type=16s rRNA (NGS)` in BioSample (owner questions 3, 4).

## 2. PRJNA46337 — "The Neonatal Microbiome and Necrotizing Enterocolitis" (dbGaP phs000247, SRP002422)

**What the evidence says**
* Package 1.12.0 state: 827 samples; health_condition `healthy_control` 808 (gmrepo 630, mbodymap 178) and `nec` 19 (mbodymap);
  health_condition_detail "Enterocolitis, Necrotizing" 165 (gmrepo) + "Enterocolitis, Necrotizing [MeSH D020345]" 15 (mbodymap)
  + "Health" 574 (gmrepo). registry_biosamples holds 0 rows for this study, so no R1 route existed.
  (The task brief cites 139 `nec` samples; the package carries 19 — 139 is the number of NEC-case samples in the BioSample attributes below.)
* BioSample attributes (827 records, 74 subjects): `study_design=Case-Control`; `subject_is_affected=Yes` + `study_disease=Enterocolitis, Necrotizing`
  on 139 samples from 10 subjects; `subject_is_affected=No` and no study_disease on 688 samples from 64 subjects; no subject has mixed flags.
  The condition is therefore stated per sample (per subject), not only as the study topic.
* Papers: Europe PMC hits for phs000247 — PMC5553277 (Warner 2016, Lancet; case-control, "Cases were defined as infants whose clinical
  courses were consistent", "28 developed necrotising enterocolitis; 94 infants were used as controls"), PMC4151715 (La Rosa 2014, 16S succession),
  PMC6030953 (Cronobacter carriage), PMC8953333 (ML prediction); PMC8549755 (2021) is a 124-dataset meta-analysis whose Table S1 supplies the
  package's 14 `nec_status=no` rows ("NEC status=pre-NEC") — all 14 are on `subject_is_affected=Yes` samples. Full text of PMC5553277 and
  PMC4151715 was not served by Europe PMC (empty fullTextXML); abstracts were used.
* Cross-check of external labels against attributes: of the 139 NEC-case samples, 19 carry `nec` (confirmed) and 120 carry `healthy_control`
  (contradicted). All 688 control samples carry `healthy_control` (confirmed). gmrepo's detail "Enterocolitis, Necrotizing" sits on 157 control
  samples (study topic, contradicted) and 8 case samples (confirmed); "Health" sits on 116 case samples (contradicted).

**Decision**
* health_condition: recode `healthy_control` -> `nec` on 120 samples (R1 sample.attr.study_disease, confidence 0.9);
  keep `nec` on 19 (re-anchored to R1); keep `healthy_control` on 688 control samples (R1 sample.attr.subject_is_affected = No,
  Case-Control design). Nothing is retired at the health_condition level because every existing `nec` is attribute-confirmed.
* health_condition_detail: retire "Enterocolitis, Necrotizing" on 157 control samples; recode "Health" -> "Enterocolitis, Necrotizing" on
  116 case samples; keep 23 existing NEC details on case samples. The 458 "Health" details on control samples are untouched.
* `nec` is a legacy_infant code; all 827 rows are in_infant_catalog, so applying it does not mint a legacy code on non-infant samples.
* Timing: `nec` here is the subject's case status; pre-onset samples of case infants keep `nec_status=no` where PMC8549755 states pre-NEC
  (14 samples). Whether that split is the intended semantics is owner question 1.

**Counts**: 120 recode + 116 recode + 157 retire = 393 corrections; 730 keep rows.

## Totals
495 corrections (102 PRJNA50637, 393 PRJNA46337); 832 keep rows; 4 owner questions.

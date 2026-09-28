# GUT_SCOPE_REPORT — curated scope `gut_all` (release R2026.7, package 1.8.0, 2026-09-28)

Owner decision 2026-09-28: curate ALL human gut shotgun-metagenome samples (all ages), rename the catalog **Microbiome Repo**, keep the infant
catalog reproducible as a filter; other human microbiomes are future plans. Spec: config/packs/gut.yaml; vocabulary config/vocab/health_conditions.yaml.

## Scope and tables
* **2,837 studies / 579,252 samples**: 389 infant-catalog studies (154,356 curated samples copied verbatim, source `infant_catalog`) + **2,448 non-infant
  gut studies / 424,896 harvested BioSamples** (source `gut_all_v1`). Study rule: registry host human, assay shotgun, gut_stool among body sites (+ included
  infant studies). `infant_scope = true` → **72,358 samples = the infant catalog's catalog_scope exactly** (assertion F14 in the site build).
* Tables: gut_sample_determinations.parquet (1,659,128 rows; routes R1 1,173,210 · R2 142,737 · R3 32,736 (infant rows) · R4 310,445),
  gut_sample_metadata_wide.parquet (579,252 rows), gut_studies.parquet (2,837 rows). Site: gut/index.html (coverage by age category, health conditions,
  countries, largest studies, DuckDB-WASM sample explorer with an "infant catalog scope" switch).

## Coverage (all 579,252 samples → non-infant 424,896)
| field | all | non-infant |
|---|---:|---:|
| age_at_collection_days | 23.6 % | 16.8 % |
| sex | 26.8 % | 21.1 % |
| bmi | 5.3 % | 7.2 % |
| country | 89.2 % | 87.7 % |
| health_condition | 28.8 % | 36.9 % |
| antibiotic_exposure | 7.2 % | 4.4 % |
| subject_id | 34.4 % | 27.0 % |
| timepoint_label | 13.6 % | 9.4 % |

Age categories (non-infant samples): adult 208,593 · elderly 28,367 · child 25,329 · adolescent 3,868 · infant 3,054 · neonate 455 · unknown 155,230
(basis: numeric age 70,022 · sample life stage 7,271 · R4 abstract life stage 76,329 · study life stage 116,044). Body site of non-infant samples:
primary gut 377,195 (222,142 from the sample's own attribute, 178,317 because the study's only registry site is gut_stool), unknown 24,437, other-site 23,264.
Health condition (all samples, top): healthy_control 53,418, intervention_cohort 15,681, other_cancer 10,853, gi_infection_or_diarrhoea 9,818, other_disease 9,086, transplant_or_immunocompromised 8,799, other_infection 6,891, type2_diabetes 5,218.
Curated depth of the 2,448 non-infant studies: R1;R4 1,070 · R1 1,059 · R4 117 · R1;R2 57 · R1;R2;R4 39 · R2;R4 6 · R2 5 · **no committed value 95** (21 without any attribute row).

## How it was built (one wave of 15 leaves + root assembly, ≈ 2 h wall)
* **R1** (leaf): gut attribute field map — 287 keys → 7 fields (244 keys skipped with reasons), deterministic parsers (r1_parsers.py), utility model for
  key triage only (89 k tokens) → 393,111 rows; 665 disagreeing (sample, field) groups resolved by documented rules. Plus the registry's normalised
  age / sex / country rows (route R1, `registry_norm_v1`).
* **Normalisation** (leaf): 3,719 distinct disease/health pairs → 1,615 coded (20 rules + utility model, 81 % blind rule-vs-model agreement; 603 k tokens);
  456 antibiotic pairs → 263 yes/no; expansion to 51,707 R1 rows. Unspecified diabetes → type2_diabetes at 0.6 (no unspecified code).
* **R4** (5 leaves, 6.3 M tokens): abstracts (Europe PMC, ≤ 3 PMIDs) + ENA title/description → cohort-wide statements, verbatim-quote check (7–17 %
  dropped), deterministic post-filters, partial reasoning-model audits in 2 shards; ≈ 3,300 statements for ≈ 1,700 studies; expanded to samples without a
  sample-level value (confidence ≤ 0.5, evidence_limited_to_abstract = 1). `sex` from R4 dropped at assembly (pack routes R1–R3).
* **R2** (8 leaves, no model, ≈ 1.4 h each): 1,317 studies with open-access PMC papers → 1,826 PMCIDs fetched (≈ 15 % 'not open access' / no
  supplementary files; docx/pdf tables not read; members > 60 MB skipped); exact-accession gate passed for **127 studies** → 51,497 rows (37,377 committed
  after precedence). Leaves 7 extended the join keys with ENA sample_alias; several tightened the gate (tokens ≥ 3 chars, unique per study).
* **Assembly** (root, catalog.scopes.build_gut_scope): precedence infant catalog > R1 > R2 > R3 > R4; `unknown` codes are never rows; pack routes enforced;
  26,322 conflicts logged (mostly two R1 age keys; higher confidence wins).

## Deviations / caveats to carry
* Non-infant studies have **no R3** (full-text prose) and **no Opus group audit** of R4 statements (group_audit pending / partial Sonnet-class audits).
* Age: bare numbers under age/host_age read as YEARS (R1 leaf, conf 0.7, 52,628 rows); ages > 120 y nulled upstream; 2 studies flagged possibly mis-united.
* health_condition for case-control cohorts is left unknown at cohort level (groups in health_condition_detail); intervention_cohort is a design flag, not a disease.
* R2 covers only xlsx/csv/tsv supplements with exact-accession joins (127 of 1,317 OA studies); two-table joins (participant ↔ sample) are out of scope.
* 95 non-infant studies carry no committed value; 155,230 non-infant samples have no age category.
* The registry rows for 12,288 BioSamples shared between an infant study and another BioProject are assigned to the infant study (curated wins).
* Repository names / URL unchanged (PAT lacks Administration permission); the catalog name lives in config/site.yaml.

## LLM cost of this phase
R1 key triage 0.09 M · normalisation 0.60 M · R4 6.3 M · R2 0 → **≈ 7.0 M tokens** for 424,896 newly curated samples.

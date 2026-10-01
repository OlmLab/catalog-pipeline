# Interventions — R2026.15 (package 1.14.0)

Owner request (2026-10-01): categorise studies by intervention, so that e.g. *health condition = IBD* and *intervention = probiotic* can be combined.

## What was built
* Vocabulary `config/vocab/interventions.yaml` — 15 study-level codes + `placebo` / `no_intervention` (sample level only). Only interventions the investigators ADMINISTER count; observed routine treatment stays in `medication` / `antibiotic_exposure`.
* **Study level** (`gut_studies.interventions` + `intervention_design`, `intervention_detail`, `population_condition`, evidence quote; route R4, confidence 0.5–0.55): all 2,886 catalog studies, 12 leaves, title + BioProject description + up to 3 Europe PMC abstracts (64 % of studies had ≥ 1 abstract), two independent reasoning-model replicates; a code is committed when both return it (study-level identical code sets 92–98 % per shard), single-replicate codes in `interventions_unreplicated`; verbatim-quote check; deterministic guards (no code from a disease word; antibiotics/diet/surgery need an administration cue; transplants into animals, in-vitro systems and donors excluded — 11 animal-FMT codes were additionally demoted at assembly).
* **Sample level** (field `intervention` + `intervention_detail`, route R1): archive attributes that record a subject's arm, FMT-recipient status or pre/post timing — 187 accepted keys in 121 studies → 20,242 samples (no_intervention 8,191 · diet_intervention 3,239 · drug_therapy 1,822 · antibiotic 1,678 · prebiotic_or_fibre 1,425 · fmt 1,389 · placebo 898 · probiotic 438 …). 6,555 arm-only rows have no timing key and may include baselines (flagged in parse_note).
* `health_condition = intervention_cohort` is recoded to the study's `population_condition` wherever that is known (all routes); the code remains only for studies whose population condition is not stated.

## Results
785 of 2,886 studies administered at least one intervention: fmt 162, diet_intervention 136, drug_therapy 108, probiotic 104, antibiotic 103, prebiotic_or_fibre 61, surgery 57, other_intervention 50, dietary_supplement 48, vaccine 19, synbiotic 13, live_biotherapeutic 13, exercise 12, bowel_preparation 8, phage_therapy 4.

Examples of combinations now filterable (study counts, population condition × intervention): ulcerative colitis × FMT 36; GI infection (mostly C. difficile) × FMT 37; obesity × diet 26, × surgery 19; type 2 diabetes × drug therapy 14; Crohn's disease × probiotic (PRJNA1216426, B. breve Bif195 vs placebo).

## Limits (not assessed at this depth)
* 12 studies of shard 0 were not classified (token stop): PRJEB6092, PRJNA1020557, PRJNA1153928, PRJNA1227979, PRJNA1269031, PRJNA361402, PRJNA484031, PRJNA532645, PRJNA693850, PRJNA728374, PRJNA922086, PRJNA946655; PRJNA352220 was refused by the model. Their `interventions` is empty = not assessed, not "none".
* 36 % of studies have no linked abstract and were judged from the title and BioProject description only; full texts were not read (an R3 pass would add arms and doses).
* Study-level codes say what a study gave, not which samples received it; use the sample-level `intervention` field for arms where the archive records them.
* Leaves batched 4–6 studies per request to fit the token cap; overlong verbatim quotes were trimmed to 12-word windows.

Cost: ≈ 14.6 M billable tokens (12 study leaves) + 0.6 M (arms leaf).

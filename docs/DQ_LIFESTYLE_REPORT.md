# DQ report — study-level lifestyle codes (R2026.13 / package 1.13.0 prep)

Scope: every study whose `lifestyle` code was assigned cohort-wide from a study-level statement (routes R3/R4) in package 1.12.0
(`gut_sample_determinations.parquet`, field `lifestyle`, route in R3/R4): **69 studies, 8,883 samples**
(one statement per study; no study carries two study-level codes). R1 attribute-derived codes (1,775 samples) were out of scope.

## Method
1. Inputs per study: the statement's verbatim quote, evidence source/route/confidence, the full ENA study title and description
   (fetched from the ENA portal, 69/69), the linked paper's title and abstract from Europe PMC for the 43 paper-sourced
   statements, the catalog's per-study health_condition and country counts (to surface case–control arms), the code definition and the
   whole `lifestyle.yaml` vocabulary with its note.
2. **Deterministic guard**: the quote must contain at least one `match_terms` entry for its code (case-insensitive, word-start
   boundary, up to three trailing letters so plurals count). `other_lifestyle` has no match terms and is exempt from the guard
   (model decision only). Guard result: pass 47 / fail 22 (2 of the fails are `other_lifestyle`).
3. **Rubric model** (role `rubric`, Sonnet-class via `catalog.models.resolve_model`), one request per study, JSON
   {decision, new_code, confidence, applies_to, reason, quote_check}. 69/69 answered (3 needed a retry with a larger output budget after an
   empty response at max_tokens=1500). `quote_check` was verbatim in the supplied text for 67/69 studies;
   the other 2 had confidence capped at 0.75.
4. Combination: guard fail → `retire` regardless of the model (model `keep` at ≥0.7 becomes an owner question; a model `recode` whose
   new code has vocabulary support in the quote or context is applied instead). Guard pass → model decision; a `recode` is applied only
   when the new code has a vocabulary match in the quote or study text, otherwise `retire` + owner question.
   Retiring a study's `lifestyle` also retires its `lifestyle_detail` rows from the same statement locator (22 studies, 4,647 sample rows).

## Decisions (69 studies)
| action | studies | samples |
|---|---|---|
| keep | 42 | 3,963 |
| retire | 25 | 4,892 |
| recode | 2 | 28 |

Retire breakdown: 4 model-retire with guard pass (arm-only / clinical / not stated), 7 model-retire with guard fail, 13 guard-only retire (model kept, quote lacks a match term — mostly `athlete` statements that name the sport or "players" rather than a vocabulary term; listed as owner questions).
Model decisions alone: keep 55, retire 11, recode 3.
Recodes applied: pastoralist → rural_non_industrialized (1), traditional_agriculturalist → pastoralist (1).

### By code
| old_value                   |   keep |   recode |   retire |   samples |
|:----------------------------|-------:|---------:|---------:|----------:|
| athlete                     |      6 |        0 |        6 |       691 |
| extreme_environment         |      3 |        0 |        1 |       175 |
| hunter_gatherer             |      3 |        0 |        1 |       137 |
| indigenous_community        |      3 |        0 |        1 |       152 |
| institutionalized           |      5 |        0 |        3 |      1944 |
| military                    |      2 |        0 |        1 |       508 |
| other_lifestyle             |      0 |        0 |        2 |       427 |
| pastoralist                 |      0 |        1 |        2 |        88 |
| rural_non_industrialized    |     11 |        0 |        2 |      3321 |
| spaceflight_or_analog       |      1 |        0 |        1 |        12 |
| traditional_agriculturalist |      1 |        1 |        0 |       103 |
| transitional_or_migrant     |      0 |        0 |        3 |       306 |
| urban_industrialized        |      6 |        0 |        2 |       931 |
| vegetarian_or_vegan         |      1 |        0 |        0 |        88 |

Patterns the model flagged (see `rationale` per study in the parquet): codes describing one arm applied to a cohort with controls
(institutionalized, athlete, military, transitional_or_migrant), `other_lifestyle` used for clinical / exposure descriptors (both retired),
and `urban_industrialized` where the source did not say urban/industrialized/westernized (2 of 8 retired; 6 kept where the text states it).

## What is NOT changed
* R1 (attribute) lifestyle codes; sample-level statements; `lifestyle_detail` where the code was kept or recoded.
* No value was invented: `recode` rows point to a vocabulary code whose match term is present in the quote or study text.

## Owner questions
13 (OWNER_QUESTIONS_lifestyle.md): 10 guard-vs-model disagreements (guard retired, model kept at ≥0.7; codes athlete 5, indigenous_community 2, spaceflight_or_analog, pastoralist, institutionalized, military, rural_non_industrialized/urban_industrialized) where adding the quoted term to the vocabulary would restore the code; 2 keeps where the model was unsure the statement applies to all samples; 1 model recode retired because the proposed code had no vocabulary support.

## Tokens
Rubric model: uncached input 204,555 + output 36,635 = 241,190 (cache reads 337,272, not counted). 74 requests (69 + 2 pilot + 3 retries).

## Files
* `dq_corrections_lifestyle.parquet` — 91 rows (69 lifestyle + 22 lifestyle_detail companions), schema per task contract (sample_key '' = whole study).
* `dq_lifestyle_diagnostics.csv` — same 69 studies with guard hits, model decision/new_code/confidence/applies_to, n_samples, route.
* `OWNER_QUESTIONS_lifestyle.md`

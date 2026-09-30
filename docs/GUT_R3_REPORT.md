# Gut scope — route R3 (full-text cohort statements) — R2026.8 / package 1.9.0 (2026-09-28)

## What ran
* 24 leaf workers ("Gut R3 00–23", ≈ 55 studies each) over the 1,317 non-infant gut studies with a PMC full-text paper, plus 3 completion workers for 54 studies that had received one replicate or none under the per-worker token stop. One shard (09, 55 studies) was stopped by the model provider's content filter and was not retried — those studies have no R3 rows.
* Per study: first PMCID only; Europe PMC full-text XML → Methods → abstract → Results, one chunk ≤ 36 k chars (many workers shrank the chunk to 9–30 k chars to fit the 1.5 M-token stop; 362 studies were read with < 16 k chars). Two independent Sonnet-class replicates (`resolve_model('rubric')`; the API rejects `temperature`, so replicates differ by system preamble); a statement is committed only when both replicates agree on (field, value, applies_to = all) and its ≤ 12-word quote is a verbatim substring. Deterministic guards (age range within one life-stage category; antibiotic exclusion window ≥ 1 month; `healthy_control` needs healthy/control wording; no cohort-level disease code for case–control designs; recruitment-site country only) were applied by every worker.
* Cost: ≈ 36 M tokens as summed from the 26 completed leaves (leaf accounting varies — most totals include prompt-cache reads, so billable tokens are lower) (≈ 32 k per full-text study); wall ≈ 35 min for the main wave, 11 min for completion.

## Outputs (microbiome_repo-pipeline `data/inputs/gut/r3/`, merged by `catalog.scopes.merge_r3_shards`)
* `gut_r3_determinations_merged.parquet`: **1,871 study-level statements over 789 studies** (of 1,138 with full text; 1,262 attempted). Per field: {'country': 596, 'life_stage': 366, 'health_condition': 315, 'health_condition_detail': 274, 'antibiotic_exposure': 241, 'sex': 77, 'age_at_collection_days': 2}. Sections: {'paper.fulltext.methods': 1515, 'paper.fulltext.abstract': 234, 'paper.fulltext.results': 122}. Confidence: {0.7: 1721, 0.6: 141, 0.5: 9}. 8 double health-condition codes resolved (disease code kept over `intervention_cohort`; alternative in `parse_note`).
* Health-condition codes (top): {'healthy_control': 133, 'other_cancer': 29, 'other_disease': 25, 'obesity': 23, 'gi_infection_or_diarrhoea': 15, 'type2_diabetes': 13, 'colorectal_cancer': 12, 'transplant_or_immunocompromised': 9, 'cardiometabolic_other': 9, 'other_infection': 7}. Life stages: {'adult': 291, 'child': 33, 'elderly': 17, 'adolescent': 11, 'mixed_ages': 9, 'infant': 5}.
* Side tables (not expanded to samples): `gut_r3_subgroups_all.parquet` 2,754 case/control and subgroup statements; `gut_r3_unreplicated_all.parquet` 753 single-replicate statements (confidence 0.4); `gut_r3_study_summary_all.parquet` per-study design / n subjects / age range / sample type; `shards/` raw leaf files and token costs.

## Effect on the package (1.8.0 → 1.9.0, all 579,252 gut samples)
* Determinations 1,659,128 → 1,787,854; R3 sample rows 161,462 (32,736 infant + 128,726 new).
* Coverage: antibiotic exposure 7.2 % → 12.5 %, health condition 28.8 % → 31.0 %, sex 26.8 % → 28.6 %, country 89.2 % → 90.1 %; age category unknown 222,970 → 212,459 (basis `r3_fulltext_life_stage` precedes `r4_abstract_life_stage`).
* infant_scope unchanged: 72,358. Infant tables unchanged.

## Limits / next
* Only the first PMCID was read; re-analysis / benchmark papers as first PMCID yield nothing (a paper-relation gate would help).
* Truncated chunks for 362 studies and the blocked shard (55 studies) are the first candidates for a re-run with a larger per-worker budget.
* Case–control cohorts stay unknown at sample level unless R1/R2 give per-sample groups; the subgroup table holds the group statements for a future R2-style join on sample naming patterns.
* No Opus group audit was run on R3 rows (`group_audit` null).

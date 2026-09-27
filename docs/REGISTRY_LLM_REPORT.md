# REGISTRY_LLM_REPORT — scale-up S1b (release R2026.4, package 1.6.0)

LLM classification of the **human-candidate studies** of the registry universe: `candidate_class ∈ {prior_human, signal_human_new, ambiguous_new}`
and deterministic `needs_llm` → **6,406 studies** (867,063 runs), split into 22 interleaved shards of 291–292 studies, one leaf worker each
(`catalog.registry.run_llm_shard.run_shard`, pipeline main fe4e598). Cascade: two rubric replicates (role `replicate`, claude-sonnet-5, batches of 6,
forced tool call) → adjudication of disagreements (role `adjudicate`, claude-opus-5-5, `tool_choice auto`). Studies without a human signal
(`nosignal_new`, 42,973) and prior non-human studies (3,676) were **not** sent to the LLM (owner decision): they keep their deterministic stage.

## Shard fan-out (first pass)

| shard | studies | sonnet_x2 | opus_adjudicated | pending | tokens | validator problems |
|---|---:|---:|---:|---:|---:|---:|
| 00 | 292 | 204 | 60 | 28 | 795,202 | 37 |
| 01 | 292 | 213 | 66 | 13 | 826,231 | 38 |
| 02 | 292 | 219 | 49 | 24 | 800,784 | 51 |
| 03 | 292 | 221 | 47 | 24 | 802,247 | 57 |
| 04 | 291 | 187 | 80 | 24 | 831,921 | 61 |
| 05 | 291 | 207 | 78 | 6 | 822,697 | 57 |
| 06 | 291 | 205 | 68 | 18 | 848,854 | 68 |
| 07 | 291 | 202 | 77 | 12 | 827,056 | 53 |
| 08 | 291 | 211 | 56 | 24 | 795,969 | 61 |
| 09 | 291 | 218 | 55 | 18 | 810,220 | 44 |
| 10 | 291 | 225 | 48 | 18 | 818,147 | 59 |
| 11 | 291 | 210 | 39 | 42 | 836,908 | 74 |
| 12 | 291 | 218 | 43 | 30 | 820,045 | 47 |
| 13 | 291 | 196 | 65 | 30 | 802,161 | 45 |
| 14 | 291 | 202 | 71 | 18 | 820,243 | 64 |
| 15 | 291 | 193 | 80 | 18 | 810,367 | 49 |
| 16 | 291 | 202 | 66 | 23 | 841,176 | 36 |
| 17 | 291 | 232 | 35 | 24 | 789,178 | 54 |
| 18 | 291 | 220 | 71 | 0 | 827,797 | 40 |
| 19 | 291 | 211 | 56 | 24 | 817,199 | 53 |
| 20 | 291 | 203 | 72 | 16 | 828,689 | 54 |
| 21 | 291 | 208 | 78 | 5 | 829,333 | 51 |

First pass: 18,002,424 tokens (≈ 2,810 per study), 22 leaves × 18–26 min wall. **439 studies (6.9 %) came back `pending`**: whole adjudication
batches of the Opus-class model returned 0 tokens (transient host.llm errors and, for a few batches, `stop_reason=refusal`), and the first-pass
driver replaced the merged replicate row by a blank sentinel when adjudication failed (no per-stage resume, replicate rows not persisted).

## Fix and pending pass

Pipeline commit a8d7bca: unresolved adjudications are re-requested as **singleton** batches (2 rounds), still-unresolved studies fall back to a
**conservative replicate merge** (values the two replicates agree on are kept, disagreeing fields → `unknown*`, union of sites/stages,
intersection of flags, confidence = min/2; stage stays `pending`, outcome `replicates_unadjudicated`), and both replicate row sets are persisted
in the shard json. The 439 pending accessions were re-run as one shard with this driver: 1,494,575 tokens, 582 s;
stages sonnet_x2 288 / opus_adjudicated 108 / pending 43 (40 conservative merges, 3 double sentinels). Retry rounds: 109 singleton re-requests
resolved most first-round failures (271k tokens); 47 second-round singletons returned 0 tokens again (persistent refusals/errors).

## Result over the 6,406 LLM-eligible studies

| classification_stage | studies |
|---|---:|
| sonnet_x2 | 4,895 |
| opus_adjudicated | 1,468 |
| pending | 43 |

| host_human | studies |
|---|---:|
| yes | 4,987 |
| no | 985 |
| mixed | 227 |
| unknown | 207 |

Primary body site (LLM set):

| body_site_primary | studies |
|---|---:|
| gut_stool | 1,993 |
| unknown_site | 957 |
| blood_tissue | 815 |
| respiratory_lower | 434 |
| oral | 375 |
| vaginal_urogenital | 178 |
| skin | 176 |
| nasal_nasopharyngeal | 174 |
| multi_site | 139 |
| other_site | 121 |
| eye_ear | 47 |
| milk | 12 |

Primary life stage (LLM set):

| life_stage_primary | studies |
|---|---:|
| unknown_age | 4,201 |
| adult | 736 |
| child | 249 |
| mixed_ages | 75 |
| infant | 72 |
| elderly | 43 |
| neonate | 26 |
| adolescent | 19 |

Total LLM spend for S1b: **19,496,999 tokens** (≈ 3,044 per eligible study, ≈ 3,050 with the pending pass).

## registry_studies.parquet (package 1.6.0): 54,410 studies

| classification_stage | studies |
|---|---:|
| deterministic_rule | 43,163 |
| sonnet_x2 | 4,895 |
| deterministic_prior | 4,841 |
| opus_adjudicated | 1,468 |
| pending | 43 |

| host_human | studies |
|---|---:|
| no | 40,065 |
| unknown | 7,931 |
| yes | 6,187 |
| mixed | 227 |

Scope sizes: human_all 4,576, gut_adult 1,185, blood_tissue 1,038, unknown_site 823, respiratory 718, oral 565, infant_gut 389, gut_child 356, vaginal_urogenital 262, skin 242, other_site 226, milk 62.

## Deviations and caveats (carry forward)

* 43 LLM-eligible studies remain `pending` (0.7 % of the LLM set; 0.08 % of the registry); 40 of them carry conservative replicate-merge values
  (`outcome = replicates_unadjudicated`), 3 are blank sentinels. Their host / site / stage values are provisional.
* `life_stage_primary = unknown_age` for 4,201 of the 6,406 LLM-classified studies: ENA study/sample
  records rarely state age; the registry is archive-only (route R1). `body_site_primary = unknown_site` for 957.
* The 49 infant-universe studies that the ENA library filters never surface (incl. the included PRJNA61745) are carried from the infant tables
  (`found_by = infant_catalog_carry`, stage `deterministic_prior`, assay unknown) so the registry is a superset of the screened infant universe.
* Enumeration deviations stand (ENUMERATION_REGISTRY_REPORT.md): S3 narrowed (no GENOMIC × tax 9606 human-genome runs), METATRANSCRIPTOMIC not pulled.
* Validator problems (evidence rows failing the ≤12-word / labelled-source rules) were downgraded to sentinels per pipeline rules; counts per shard above.
* Leaves 17 and 19 issued a few retry requests outside the driver (not in their cost logs); first-pass leaf costs are otherwise from the driver's cost summaries.

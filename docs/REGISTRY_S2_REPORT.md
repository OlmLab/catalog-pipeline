# REGISTRY_S2_REPORT — scale-up S2, registry sample tier (release R2026.5, package 1.7.0, 2026-09-27)

## What was built
* **BioSample attribute harvest** for the 4,217 `human_all` registry studies outside the curated infant catalog: 612,857 BioSamples in
  registry_biosample_index → **611,601 harvested** (99.8 %; ENA browser XML in batches of 100, NCBI BioSample for the misses), 13,490,344
  attribute rows, 6,191 distinct normalised keys. Four leaves × ≈ 153k samples, 2 ENA workers each, 48–51 samples/s, ≈ 52 min wall.
  1,264 accessions unresolvable (shards 0 and 3 did not use the esearch rescue route that shards 1 and 2 used — ≈ 1,100 of them are probably
  recoverable; carry as a deviation). Same-digit identifier substitutions by ENA (unknown SAMD → SAMN) and NCBI efetch were caught by an
  identifier guard in every leaf (≈ 1,150 wrong records dropped).
  Working_data artifact: registry_biosample_attributes.parquet (132 MB).
* **Normalisation**: 42,989 distinct (field, key, value) pairs for age / body_site / sex / country → utility model (Haiku-class), batches of 40,
  6 leaves, **9,148,959 tokens** (≈ 213 per pair), 11 null outputs. Pair-level vocabulary share: body_site 43 % (many pairs are non-site
  values under site-like keys), age 93 %, sex 87 %, country 94 %; **sample-weighted**: body_site 74 %, age 86 %, sex 99.6 %, country 99.4 %.
  Map artifact: registry_pairs_normalised.parquet.
* **registry_biosamples.parquet** (611,601 rows): body_site_code known for 51.6 % of samples (unknown_site for a
  further 9.7 %; no site attribute for the rest), life stage 16.5 %,
  sex 19.5 %, country 82.2 %, collection year 75.7 %,
  disease text 9.3 %. Age in days for 56,918 samples (median 34 y).
  Top sites: gut_stool 211,237, unknown_site 59,410, blood_tissue 27,535, oral 20,986, respiratory_lower 15,022, skin 13,784. Top countries: US 153,792, CN 87,897, GB 38,269, SE 19,222, DE 15,292.
* **Study roll-up / refinement** (deterministic, build_biosamples.rollup_studies): 138 unknown body-site primaries and
  229 unknown life-stage primaries resolved from ≥ 60 % sample agreement; 367 site codes and
  614 life-stage codes added to study lists (≥ 10 % of samples, evidence source `sample.attr.<key>`).
  registry_studies now: body_site_primary unknown_site 8,273 (was 8,413), life_stage_primary
  unknown_age 11,680 (was 11,914). Scopes: human_all 4,606, gut_adult 1,366, blood_tissue 1,162, respiratory 776, unknown_site 658, oral 592, gut_child 393, infant_gut 389, vaginal_urogenital 269, skin 259, other_site 252, milk 62.
* **Papers / authors / BioProject** (leaf S2-B, docs/REGISTRY_S2_PAPERS.md): 6,398 study × paper links (2,676 of 4,217 studies = 63.5 %,
  90.1 % open access), 4,217 BioProject records (384 with declared publications), 52,110 author rows (18,527 ORCID). 9,569 requests, 48 min.
* **Sandpiper join**: 838,702 of 1,980,623 registry runs (42.3 %) have a Sandpiper 2.0.0 profile; human_all 48 %, gut_adult 57 %, infant_gut 49 %.
  Column n_runs_sandpiper on registry_studies.
* Curated-verdict precedence: included infant studies are always in human_all (4,606 now), assay shotgun_dna.

## Cost (S2, this session)
Harvest and papers: API calls only. LLM: pilot normalisation 0.53 M + full normalisation 9.15 M tokens (utility model). Total S1+S2 LLM
spend this session ≈ 29.2 M tokens.

## Deviations / caveats to carry
* Pair-level normalisation cannot use sibling attributes (e.g. `host_age_units`): bare numeric ages under `age`/`host_age` were read as years;
  ages > 120 y were nulled (unit errors). Age coverage (17 %) reflects what submitters deposited.
* `disease_raw` is free text (no vocabulary yet); `collection_year` is a regex year.
* Study refinement only touches unknown primaries / adds list codes; it never contradicts a committed study-level value.
* 1,264 unresolvable BioSamples (0.2 %); ≈ 1,100 recoverable via NCBI esearch [accn] → efetch (harvest shards 0 and 3).
* Curated infant studies (389) are not in registry_biosamples (their per-sample data lives in the curated tables).
* Registry side tables (papers/authors/BioProject) carry weaker link confidence than the curated study_paper_links (no section mining).

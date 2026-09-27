# REGISTRY_S2_PILOT.md — S2 pilot A: BioSample attribute harvest + normalisation-cost measurement

*2026-09-27. Pipeline: OlmLab/catalog-pipeline main 64a97fc. Inputs: `registry_biosample_pilot_ids.parquet` (11,752 rows = 11,724 distinct BioSamples, ≤3 per study over the 4,217 human_all studies not in the infant catalog; 28 accessions occur under two studies), `registry_human_all_studies.parquet` (4,576 studies, `body_site_primary`). All numbers below are read from the tables saved with this report.*

## 1. Method
* **Harvest** (`harvest_pilot.py`, adapted from `src/catalog/harvest/harvest_samples.py`): ENA browser sample XML, 100 accessions per request, 3 concurrent workers through `harvest_lib.fetch_many` (cache-through, per-host limiter, 429/5xx backoff); misses → NCBI BioSample `efetch` (batch 200, then batch 50, then single-id retries), then one ENA request on the secondary accessions of the remainder. `CATALOG_CACHE_DIR` pointed inside the workspace. Change vs the pipeline script: the requested accession is matched against **every identifier in the returned record** (PRIMARY_ID / SECONDARY_ID / EXTERNAL_ID / NCBI `Ids/Id`), not only the `accession` attribute — see the trap in §6.
* **Field assignment** (`fields.py`): normalised keys are mapped to six R1 target fields by rule (age keys = `life_stages.yaml → age_attribute_keys` ∪ `attribute_field_map.csv` age keys ∪ keys with an `age` token, minus unit/gestational/maternal/donor keys; sex = `sex|gender` token; body site = `body_site|body_habitat|body_product|isolation_source|env_medium|tissue|sample_type|anatomical|env_local_scale|…` (biome and `env_broad_scale` excluded); disease = `disease|health|diagnosis|phenotype|condition|disorder|infection|case_control`; country = `geo_loc*|geographic_location*|country`; collection date = `collection_date|collection_timestamp|…`). A value is **non-empty** when it is not an INSDC placeholder (`missing`, `not collected`, `not applicable`, `NA`, `unknown`, `restricted access`, …; regex in `fields.py`).
* **Normalisation pilot**: distinct non-placeholder (key, value) pairs of the four vocabulary fields, stratified: all 48 sex pairs, all 590 age pairs, random 1500 of 2454 body-site pairs, random 862 of 1347 country pairs (seed 0) = 3,000 pairs. Utility model (`host.llm` default, Haiku-class), batches of 40 pairs, forced tool call with a JSON schema whose enums are the codes of `config/vocab/body_sites.yaml` / `life_stages.yaml` and {female, male, unknown}; ISO-3166 alpha-2 validated against `pycountry`. Four concurrent requests.

## 2. Harvest counts
| quantity | value |
|---|---:|
| pilot rows / distinct accessions | 11,752 / 11,724 |
| samples harvested (≥1 attribute row) | **11,671** (99.55% of distinct) |
| found in ENA sample XML | 11,069 |
| found only via NCBI BioSample efetch | 602 |
| unresolvable in both archives | 53 (SAMD 34, SAME 16, SAMN 3) |
| wrong records returned by ENA and dropped | 30 (§6) |
| attribute rows (one per sample × key × value) | **239,877** (20.6 per sample; median 18 keys per sample) |
| HTTP requests | **227** (ENA batches 118, 0 errors; NCBI efetch 108; ENA secondary 1) |
| wall time | **171 s** (ENA pass 119 s = 1.01 s per 100-sample batch at 3 workers; NCBI passes 50 s, of which 44 s for 100 single-id retries) |
| throughput | 68.4 harvested samples / s |
| output | `registry_biosample_pilot_attributes.parquet` (1.84 MB; columns sample_accession, study_accession, attr_key, attr_key_norm, attr_value, attr_units, source, taxon_id, scientific_name, title, description, collection_date, geo_loc_name) |

Sample-level column fill (share of harvested samples): taxon_id 1.000, scientific_name 1.000, title 0.974, description 0.498, collection_date 0.906, geo_loc_name 0.911 (raw, placeholders included).

## 3. Attribute keys and pairs
* distinct normalised keys: **5,966** (5,951 after removing 27 structural keys such as title/alias/center_name/taxon fields); distinct (key, value) pairs: **70,859** (35,521 non-structural). Full frequency table: `registry_pilot_attribute_keys.csv`; pair table with sample/study counts: `registry_pilot_distinct_pairs.parquet`.
* keys per target field: {'age': 49, 'body_site': 36, 'collection_date': 5, 'country': 11, 'disease': 166, 'sex': 13}; non-placeholder distinct pairs per target field: {'collection_date': 3013, 'body_site': 2454, 'country': 1347, 'disease': 804, 'age': 590, 'sex': 48}.

Top 30 non-structural keys:

| attr_key_norm                          |   n_samples |   n_studies |   n_distinct_values | field           |
|:---------------------------------------|------------:|------------:|--------------------:|:----------------|
| organism                               |       11066 |        3987 |                 344 | nan             |
| collection_date                        |       10572 |        3778 |                2976 | collection_date |
| geo_loc_name                           |        8567 |        3079 |                1228 | country         |
| lat_lon                                |        8024 |        2861 |                2042 | nan             |
| host                                   |        7944 |        2854 |                 182 | nan             |
| isolation_source                       |        4989 |        1846 |                1142 | body_site       |
| scientific_name                        |        3145 |        1111 |                 126 | nan             |
| env_medium                             |        2529 |         894 |                 365 | body_site       |
| env_broad_scale                        |        2512 |         890 |                 386 | nan             |
| env_local_scale                        |        2508 |         888 |                 483 | body_site       |
| geographic_location_country_and_or_sea |        2088 |         729 |                  85 | country         |
| isolate                                |        1542 |         623 |                 941 | nan             |
| project_name                           |        1485 |         519 |                 512 | nan             |
| geographic_location_longitude          |        1321 |         459 |                 400 | nan             |
| geographic_location_latitude           |        1321 |         459 |                 397 | nan             |
| source_material_id                     |        1225 |         420 |                1108 | nan             |
| host_subject_id                        |        1060 |         367 |                 926 | nan             |
| sex                                    |         994 |         368 |                  25 | sex             |
| host_age                               |         978 |         347 |                 279 | age             |
| common_name                            |         974 |         344 |                  74 | nan             |
| host_sex                               |         920 |         325 |                  13 | sex             |
| age                                    |         894 |         329 |                 205 | age             |
| sequencing_method                      |         875 |         305 |                 113 | nan             |
| host_disease                           |         855 |         327 |                 323 | disease         |
| investigation_type                     |         809 |         287 |                  10 | nan             |
| environment_material                   |         777 |         272 |                  92 | nan             |
| environment_feature                    |         759 |         266 |                 114 | nan             |
| environment_biome                      |         757 |         266 |                  98 | nan             |
| environmental_medium                   |         579 |         200 |                  93 | nan             |
| broad_scale_environmental_context      |         576 |         199 |                  91 | nan             |

## 4. Coverage of the R1 target fields
Overall (denominator = 11,671 harvested distinct samples; last column uses all 11,724 pilot samples):

| field           |   n_key_present |   n_nonempty |   share_key_present |   share_nonempty |   share_nonempty_of_pilot |
|:----------------|----------------:|-------------:|--------------------:|-----------------:|--------------------------:|
| age             |            1949 |         1797 |              0.167  |           0.154  |                    0.1533 |
| sex             |            2061 |         1852 |              0.1766 |           0.1587 |                    0.158  |
| body_site       |            8133 |         7436 |              0.6969 |           0.6371 |                    0.6343 |
| disease         |            1519 |         1385 |              0.1302 |           0.1187 |                    0.1181 |
| country         |           10740 |         9928 |              0.9202 |           0.8507 |                    0.8468 |
| collection_date |           10626 |         9381 |              0.9105 |           0.8038 |                    0.8002 |

Per body-site scope of the study (`body_site_primary`; share of harvested sample–study rows with a non-placeholder value; full table incl. counts and key-present shares in `registry_pilot_coverage.csv`):

| scope                |   n_harvested |   age |   sex |   body_site |   disease |   country |   collection_date |
|:---------------------|--------------:|------:|------:|------------:|----------:|----------:|------------------:|
| ALL                  |     11671.000 | 0.154 | 0.159 |       0.637 |     0.119 |     0.851 |             0.804 |
| gut_stool            |      6571.000 | 0.177 | 0.179 |       0.610 |     0.102 |     0.868 |             0.809 |
| unknown_site         |       981.000 | 0.077 | 0.085 |       0.690 |     0.176 |     0.793 |             0.755 |
| respiratory_lower    |       921.000 | 0.072 | 0.072 |       0.656 |     0.157 |     0.830 |             0.828 |
| oral                 |       860.000 | 0.188 | 0.202 |       0.691 |     0.101 |     0.823 |             0.756 |
| blood_tissue         |       770.000 | 0.099 | 0.100 |       0.682 |     0.170 |     0.813 |             0.796 |
| vaginal_urogenital   |       429.000 | 0.168 | 0.156 |       0.583 |     0.105 |     0.795 |             0.767 |
| skin                 |       381.000 | 0.181 | 0.213 |       0.701 |     0.121 |     0.905 |             0.890 |
| multi_site           |       271.000 | 0.151 | 0.181 |       0.668 |     0.122 |     0.871 |             0.830 |
| other_site           |       200.000 | 0.110 | 0.145 |       0.645 |     0.180 |     0.870 |             0.860 |
| nasal_nasopharyngeal |       178.000 | 0.157 | 0.129 |       0.736 |     0.096 |     0.832 |             0.730 |
| eye_ear              |       120.000 | 0.175 | 0.208 |       0.617 |     0.025 |     0.867 |             0.867 |
| milk                 |        17.000 | 0.118 | 0.118 |       0.118 |     0.118 |     0.765 |             0.588 |

Reading: country and collection date are near-universal (≈85 % and ≈80 %) because they are mandatory INSDC checklist fields; a body-site-bearing key exists for 70 % of samples and carries a real value for 64 %; **age, sex and disease/health are present for only 12–16 % of samples** — for most registry samples these will have to come from study-level classification (S1) or from R2–R4 extraction, not from R1 attributes. Milk (n=17) is too small to read.

## 5. Normalisation-cost pilot
| field | pairs | vocab-code share | sample-weighted share | null outputs | invalid codes | mean confidence | tokens | tokens / 1k pairs |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| age | 590.0 | 0.968 | 0.985 | 0 | 0 | 0.88 | 104,113 | 176,463 |
| body_site | 1500.0 | 0.689 | 0.836 | 70 | 0 | 0.63 | 269,193 | 179,462 |
| country | 862.0 | 0.985 | 0.997 | 13 | 0 | 0.97 | 145,450 | 168,735 |
| sex | 48.0 | 0.750 | 0.982 | 0 | 0 | 0.89 | 11,137 | 232,021 |
| **all** | **3,000** | **0.830** | | 83 | 0 | | **529,893** (434,274 in / 95,619 out) | **176,631** |

* 77 requests, 0 failures, all stop_reason=tool_use, every pair_id returned exactly once; wall 133 s at 4 concurrent requests.
* Cost structure: 6,882 tokens per request of which ≈5,640 input — the system prompt (vocabulary definitions) + tool schema dominate, i.e. the per-pair marginal cost is small and the tokens/1k-pairs figure would fall roughly in proportion to a larger batch size or with prompt caching (not measured here).
* Body site is the hard field: 68.9% of distinct pairs get a code, but 83.6% of the *samples* behind them do — the uncoded pairs are mostly rare `env_medium` / `env_local_scale` / `isolation_source` values without body-site content (culture media, ENVO habitat terms, sample-type words). Most frequent pairs coded `unknown_site`:

| attr_key_norm    | attr_value                       |   n_samples |
|:-----------------|:---------------------------------|------------:|
| env_medium       | ENVO:00002003                    |          65 |
| env_local_scale  | hospital                         |          31 |
| env_medium       | swab                             |          19 |
| env_medium       | ENVO:00010483                    |          18 |
| env_medium       | biofilm material [ENVO:01000156] |          17 |
| isolation_source | hospital                         |          17 |
| isolation_source | human                            |          15 |
| env_local_scale  | ENVO:2100002                     |          15 |

* Age: 554 of 590 pairs received a numeric `age_days`; life-stage distribution {'adult': 288, 'elderly': 108, 'child': 77, 'infant': 43, 'adolescent': 38, 'unknown_age': 19, 'neonate': 15, 'mixed_ages': 2}. Numeric ages with unit keys are deterministic in the existing `attribute_field_map.csv` machinery and need not go to the LLM at all.
* Sex: the 12 uncoded pairs are numeric codes (`0/1/2`), single letters `w/B/G` and pooled samples — correctly `unknown` under the evidence rules.
* Country: 13 nulls, all for values without a country (Antarctica, Arctic Ocean, freezer positions, colon segments filed under `geographic_location_*`).

Output: `registry_pilot_normalised_pairs.parquet` (pair, field, n_samples, n_studies, model outputs, vocab_code / null_output / invalid_output flags), `registry_pilot_norm_usage.csv` (per-request tokens), `registry_pilot_norm_summary.csv`.

## 6. Traps found
1. **ENA browser XML returns a different sample when the requested BioSample accession is unknown to ENA**: asking for `SAMD00602893` returned `SAMN00602893` (an HMP sample, alias 346-CS-D-63716); 30 such records came back in the pilot. Matching on the returned `accession` attribute alone (as `harvest_samples.py` does) leaves orphan rows under the wrong accession; the harvest must verify that one of the returned identifiers is the requested one. Recommend porting the identifier check to `harvest_samples.py`.
2. `Ids/Id` and `IDENTIFIERS` matching also resolves inputs given as ERS/SRS/DRS secondary accessions.
3. 53 accessions (0.45%) are in neither archive's XML (mostly recent DDBJ `SAMD` and a few `SAMEA`); NCBI efetch returned empty `BioSampleSet` for some SAMN — likely suppressed/withdrawn records. Expect ≈0.45 % unresolvable at scale.

## 7. Extrapolation to the full registry
Assumptions: harvest rate as measured (3 ENA workers, batches of 100, 1.01 s per batch; ENA miss share 5.58% handled by NCBI batches of 200; 0.85% single-id retries at 0.44 s); attribute rows 20.55 per sample and 7.7 parquet bytes per row; distinct-pair growth by a Heaps-law fit on nested subsamples of the pilot (target-4 fields β = 0.627, disease β = 0.841, all keys β = 0.798; points [(500, 618), (1000, 1052), (2000, 1775), (4000, 2711), (8000, 3814), (11671, 4439)]). **The pair counts are upper bounds** because the pilot samples ≤3 per study and therefore over-represents between-study diversity; the remaining samples fall into studies already seen. Normalisation tokens = pairs × 176,631 / 1,000 at the measured batch-40 cost (no caching, no deterministic pre-pass).

| quantity | 614,505 new human_all BioSamples | 1,033,506 registry BioSamples |
|---|---:|---:|
| ENA batches | 6,146 | 10,336 |
| harvest wall time (measured rate) | 8,632 s = 2.4 h | 14,518 s = 4.03 h |
| harvest wall time with 2× throttling contingency | 4.8 h | 8.07 h |
| attribute rows | 12,630,076 | 21,241,909 |
| attributes parquet (MB, compressed as in the pilot) | 97 | 163 |
| expected unresolvable accessions | 2,778 | 4,672 |
| distinct pairs, 4 vocabulary fields (upper bound) | 58,276 | 80,735 |
| distinct pairs, disease/health (upper bound) | 26,574 | 41,147 |
| distinct pairs, all keys (upper bound) | 1,763,617 | 2,670,439 |
| normalisation tokens, 4 fields (upper bound) | 10.3 M | 14.3 M |
| normalisation tokens, 4 fields + disease (upper bound) | 15.0 M | 21.5 M |

The harvest is far cheaper than SCALE_UP_PLAN §4 assumed ("1 week wall (harvest-bound)"): at the measured rate the whole registry is a half-day job, and the attribute volume is ≈21 M rows rather than ≈30 M. The normalisation line, previously "NOT measured", is ≤ 15–22 M utility-model tokens as an upper bound at batch 40 — i.e. 7–11 leaf frames at the 2.0 M hard cap — and would drop with (a) batch 100, (b) a deterministic pre-pass for numeric ages, single-letter sex codes and the ≈84 % of geo_loc_name values in `Country: locality` form, (c) a persisted (key, value) → code dictionary so that only new pairs go to the model in monthly cycles.

## 8. budgets.yaml fragment
See `budgets_registry_s2_fragment.yaml` (keys under `registry_s2:`; not applied to the repo file):

```yaml
# FRAGMENT for config/budgets.yaml (append under top level) — S2 pilot A, measured 2026-09-27; not applied to the repo file.
registry_s2:
  measured_2026_09_27:
    pilot_samples_in: 11752
    pilot_samples_distinct: 11724
    pilot_samples_harvested: 11671
    pilot_found_ena_xml: 11069
    pilot_found_ncbi_efetch: 602
    pilot_unresolvable: 53
    harvest_requests: 227
    harvest_wall_seconds: 171
    harvest_samples_per_second: 68.4
    ena_xml_seconds_per_100_batch_3_workers: 1.01
    ena_miss_share: 0.0558
    attribute_rows: 239877
    attribute_rows_per_sample: 20.55
    parquet_bytes_per_row: 7.7
    distinct_keys: 5966
    distinct_pairs_all_keys: 70859
    distinct_pairs_target_fields_nonplaceholder: 8256
    coverage_nonempty_share:
      age: 0.154
      sex: 0.1587
      body_site: 0.6371
      disease: 0.1187
      country: 0.8507
      collection_date: 0.8038
    normalisation:
      model_role: utility (host.llm default, Haiku-class)
      pairs: 3000
      batch_size: 40
      requests: 77
      input_tokens: 434274
      output_tokens: 95619
      tokens_total: 529893
      tokens_per_1k_pairs: 176631
      tokens_per_request_mean: 6882
      vocab_code_share: 0.83
      vocab_code_share_by_field:
        age: 0.968
        body_site: 0.689
        country: 0.985
        sex: 0.75
      invalid_outputs: 0
      wall_seconds_4_concurrent: 133
  growth_model:
    target4:
      heaps_beta: 0.627
      heaps_k: 13.68
    disease:
      heaps_beta: 0.841
      heaps_k: 0.36
    all_keys:
      heaps_beta: 0.798
      heaps_k: 42.38
  growth_assumption: 'Heaps-law fit log(distinct pairs) = log k + beta*log(n_samples) on nested random subsamples of the pilot
    (500..11,671 samples). UPPER BOUND: the pilot draws <=3 samples per study, so its per-sample diversity exceeds a full-study
    harvest in which the remaining ~600k samples fall into the 4,217 studies already represented; the true count lies between
    the pilot''s own distinct pairs and this bound.'
  extrapolation:
    human_all_new_614505:
      harvest:
        samples: 614505
        ena_batches: 6146
        ena_seconds: 6202
        ncbi_batch_seconds: 114
        ncbi_single_seconds: 2316
        total_seconds: 8632
        total_hours: 2.4
        total_hours_x2_contingency: 4.8
        attribute_rows: 12630076
        parquet_mb: 97
        expected_unresolvable: 2778
      distinct_pairs_target4_upper: 58276
      distinct_pairs_disease_upper: 26574
      distinct_pairs_all_keys_upper: 1763617
      norm_tokens_target4_upper: 10293348
      norm_tokens_target4_plus_disease_upper: 14987140
    registry_all_1033506:
      harvest:
        samples: 1033506
        ena_batches: 10336
        ena_seconds: 10431
        ncbi_batch_seconds: 191
        ncbi_single_seconds: 3896
        total_seconds: 14518
        total_hours: 4.03
        total_hours_x2_contingency: 8.07
        attribute_rows: 21241909
        parquet_mb: 163
        expected_unresolvable: 4672
      distinct_pairs_target4_upper: 80735
      distinct_pairs_disease_upper: 41147
      distinct_pairs_all_keys_upper: 2670439
      norm_tokens_target4_upper: 14260304
      norm_tokens_target4_plus_disease_upper: 21528140
```

## 9. Deviations
* Normalisation covered 3,000 of the 4,439 distinct non-placeholder pairs of the four vocabulary fields (cap set by the task): body site 1500/2454, country 862/1347; age and sex complete. Disease/health and collection date were measured for coverage only (no controlled vocabulary in `config/vocab`).
* 53 of 11,724 pilot accessions could not be harvested from either archive; all counts and coverage shares use the 11,671 harvested samples as denominator unless stated.
* Distinct-pair and token extrapolations are Heaps-law upper bounds from a ≤3-per-study pilot (§7), not measurements on full studies.
* The harvest rate was measured once, on a Saturday morning UTC, with 3 concurrent ENA workers; sustained throughput at scale is unverified (hence the 2× contingency line).

# GUT_NEWFIELDS_R1_REPORT — new pack fields, pipeline + route R1 (R2026.12 / package 1.12.0 preparation)

Generated 2026-09-29 from the outputs of `catalog.scopes.newfields_r1` (data/inputs/gut/gut_r1_newfields_*.parquet) and of the pack-driven
`catalog.scopes.build_gut_scope` run against package 1.11.0 (build/gut/). Every number below is read from those files. Patch: `gut_newfields_r1.patch`
(`git diff --cached` after `git add -A src tests docs Makefile audit` on microbiome_repo-pipeline main @ 7793898; **not pushed**).

## A. Pipeline changes (patch)

* **`src/catalog/scopes/build_gut_scope.py`** — field lists come from `config/packs/gut.yaml` (`pack_fields()`: `fields`, `core_fields`, `key_fields`,
  `derived_fields` incl. `infant_only`, `compose`, `from`, vocab paths). Wide table: value + `__confidence` + `__route` for every pack field
  (24 new columns), derived `detailed_location` (site, locality, region; empty parts dropped — `compose_detailed_location`) and `collection_year`
  (leading YYYY — `collection_year()`); `n_fields_with_value` = core + key fields with a value (distribution now 0–10, median 3);
  `cov_<field>` on gut_studies for every pack field (8 new); vocabulary validation for every `type: vocab` field (`health_condition`, `lifestyle`)
  against `config/vocab/*.yaml` codes with drop counts in the summary (`vocab_dropped` = {'health_condition': 0, 'lifestyle': 0}). New inputs `--r1-newfields`,
  `--registry-runs`, `--registry-sandpiper`.
* **`gut_runs.parquet`** (new scope table, 721,678 rows, 16 columns incl. `library_source`): `build_gut_runs()` in newfields_r1 (shared by both
  scripts) — registry_runs ∩ gut studies + `sandpiper_profiled` from registry_runs_sandpiper, `sample_key` via biosample_accession / secondary_sample
  (run-unit samples keyed by run accession; 9,910 pooled-BioSample runs have no catalog sample and a null key). Verified
  column-by-column identical to the 1.11.0 reference table (artifact 8c08578a…). Study columns on gut_studies: `n_runs_total` (sum 721,678),
  `gbp_per_run_mean`, `gbp_per_run_median` (median over studies 3.91 Gbp), `instrument_models_top` (JSON, top 5), `library_layouts`
  (JSON), `sandpiper_profiled_share` (median 0.867). Registered in `audit/registry_schema.json` (table + the new wide/studies
  columns → DATA_DICTIONARY / README rows through `package_docs.py`, `extra_desc`), counted in `release_notes.py` (catalog runs row; coverage rows now
  from the pack's core + key fields, a field absent from the previous package counts 0). `make_version` lists every parquet in the package automatically.
* **`src/catalog/scopes/newfields_r1.py`** (new, route R1 for the new fields; see B) + **Makefile** target `gut-newfields-r1` (`GUT_ATTRIBUTES`,
  `GUT_LOCATION_MAP`/`GUT_LIFESTYLE_MAP` reuse, `NO_LLM`, `REVERSE_GEOCODE`); `gut-build` reads `GUT_R1_NEWFIELDS`, `REGISTRY_RUNS`, `REGISTRY_SANDPIPER`.
* **Tests** `tests/test_newfields_r1.py`: 191 cases — dates 42 accept + 40 reject + order/bound tests, coordinates 30 combined accept + 26 reject + 24 single,
  place validator, lifestyle rules, gut_runs + sequencing summary, pack_fields, detailed_location (8), collection_year (8), vocab validation, conflict
  resolution. Full suite: **423 passed, 29 skipped** (232 existing + 191 new; a `release_notes` shadowed-import bug introduced and caught by the suite was fixed).
* **docs/RUNBOOK.md** Stage 8 item 5 documents the leaf, the inputs, the maps and the reverse-geocoding guards.

## B. Route R1 — 1,153,739 determination rows

`gut_r1_newfields_determinations.parquet`: determination schema, route R1, scope sample, src_track gut_all_v1, release_added R2026.12, package_added 1.12.0,
determined_by gut_newfields_r1_v1, evidence_source `biosample.attribute:<key>`, evidence_locator = BioSample accession, evidence_quote = raw value ≤ 12 words.
Input: 1,796,485 attribute rows (artifact 2cf4da1c…) joined to sample_key through the 1.11.0 wide table (biosample_accession / secondary_sample; the 521
run-unit samples through gut_runs). Rows per field: {"collection_date": 321972, "latitude": 253651, "longitude": 253651, "location_region": 192908, "location_locality": 120914, "location_site": 7093, "lifestyle": 1775, "lifestyle_detail": 1775}.

### collection_date — keys used: ['collection_date']
Other candidate keys in DATE_KEYS (sampling_date, date_of_collection, sample_collection_date, collection_time, date_collected, collection_year, …) do not
occur on these rows; `experiment_collection_date` (72 rows: '22', 'stock') and `clinic_visit_date` are not collection dates and were not used. Day/month
order: a value with a field > 12 is unambiguous (0.9); otherwise the (study, key) group's other values settle it (`infer_dm_order`, 0.8, note); still
ambiguous → YYYY only (8 rows). Two-digit years expanded (0.8, note). ISO datetimes keep the date. Upper bound = max first_public year of the sample's runs.

Distinct-format table (attribute rows):

| format | n attribute rows |
|---|---|
| YYYY | 141053 |
| YYYY-MM-DD | 138637 |
| placeholder | 51665 |
| YYYY-MM | 22901 |
| interval YYYY/YYYY | 11977 |
| interval YYYY-MM-DD/YYYY-MM-DD | 4968 |
| interval YYYY-MM/YYYY-MM | 4889 |
| YYYY-MM-DDThh:mm | 2394 |
| interval | 800 |
| MM/DD/YYYY | 284 |
| Mon-YYYY | 25 |
| ambiguous D/M (year kept) | 8 |

Reject table (non-placeholder rejects, `gut_r1_newfields_rejects.parquet`, 2,115 rows; placeholders — 51,665 date rows,
90,634 coordinate rows — are simply no row):

| field_name | reason | n | examples |
|---|---|---|---|
| latitude/longitude | unparseable or out of range | 740 | 121.66 | 31.8; 121 | 32; East longitude 113 ° 46 '~ 114 ° 37' | North latitude 22 ° 27 ′ to 22 ° 52 ′ |
| collection_date | year < 1990 | 703 | 1984/1985; 1985/1987; 1905-07-13 |
| collection_date | year after first_public | 295 | 2225; 2229; 2218 |
| collection_date | interval start after end | 187 | 2020-04-01/2020-01-22; 2022-11-18/2021-06-01 |
| latitude/longitude | latitude out of range | 133 | 116.46 N,39.92 E |
| latitude/longitude | swapped pair: nearest place cc=NG, swapped cc=CM = sample country | 40 | 11.116550 N 4.569239 E |
| collection_date | impossible date | 17 | 2022-08-18/2023-05-33; 2022-08-18/2023-05-41; 2022-08-18/2023-05-38 |

### latitude / longitude — keys used: ['lat_lon', 'latitude_and_longitude', 'latitude+longitude', 'geographic_location_latitude+geographic_location_longitude']
Two determinations per sample, 4 decimals. Formats / outcomes (rows):

| format / outcome | n rows |
|---|---|
| DD.dd H DD.dd H | 165995 |
| placeholder | 90634 |
| pair DD.dd + DD.dd | 87696 |
| pair unparseable/out of range | 740 |
| latitude out of range | 133 |

Country consistency: Natural Earth is not available offline, so the check uses the GeoNames cities1000 nearest-place table bundled with
`reverse_geocoder` (offline). 252,423 pairs checked against the sample's `country`; 40 pairs rejected as
swapped (the swapped point lands in the sample's country, the pair itself does not); 13,870 pairs kept with `parse_note`
"nearest GeoNames place in <cc>, sample country <cc>" at confidence **0.7** instead of 0.9 (border/coastal points and Hong Kong/China, but also points that
look like the submitting centre — left to the curator).

### location_region / location_locality / location_site — keys used (20): ['geo_loc_name', 'geographic_location_region_and_locality', 'geographic_location_country_and_or_sea_region', 'geographic_location', 'geographical_location', 'geographic_location_country_region_area', 'collection_site', 'hospital', 'village', 'village_grouping', 'states', 'state', 'location_within_the_united_kingdom', 'site', 'study_site', 'region', 'census_region', 'locality', 'name_of_the_sampling_site', 'host_country_of_residence']
1,281 distinct (key, raw) strings (`n_location_strings`); INSDC country prefix stripped for the geo_loc_name-style keys; the remainder normalised by the
utility model (`claude-haiku-4-5-20251001`, 34 calls, batches of 40) → `gut_location_map.parquet` (raw, attr_key_norm, remainder, country_prefix, country_hint,
region, locality, site, is_placeholder, valid, rejected_fields, n_samples, model, note, exonyms). Validation: every output token must be a substring of the raw
string (accent-folded), a documented abbreviation expansion (US states, Chinese provinces, Canadian/Australian codes in `newfields_r1.py`) or an exonym the
model declared for a raw token whose folded similarity is ≥ 0.5 (`gut_location_exonym_map.json`, 112 pairs — e.g. NSW→New South Wales, QLD→Queensland, SA→South Australia, VIC→Victoria, WA→Washington, Ghent→Ghent).
29 strings are placeholders (acronyms, 'other', regional aggregates); 199 strings had a field dropped by the validator (typically a region the
model inferred from a city — 'Australia: Adelaide' → South Australia — never committed); 1,140 strings yield at least one field (`n_location_mapped`).
Confidence 0.85 for exact substrings, 0.75 for exonym / abbreviation cases.

Reverse geocoding (`--reverse-geocode`): 124,272 samples received a **location_region only** (admin1 of the nearest GeoNames cities1000 place, confidence 0.6,
`parse_note` "reverse-geocoded from lat_lon (GeoNames cities1000)") — 68,636 samples have a text-derived region. Localities are **never** filled
from coordinates (nearest-place lookup is wrong in dense metro areas, e.g. Edgewater NJ for a Manhattan hospital) and centroid-like points are skipped
(29 points shared by ≥ 3 studies and > 3 km from any place — the UK centroid near Moffat; 811 points > 10 km from any place — the
US centroid near Smith Center KS); the place's country must equal the sample's country. Text-derived values are never overwritten.

### lifestyle / lifestyle_detail — keys used: ['urban', 'rural_urban_status', 'community_type', 'host_diet', 'diet', 'special_diet', 'diet_type', 'population', 'community', 'tribe']
Never from ethnicity / race keys. Codes only from lifestyle-stating keys: `urban` / `rural_urban_status` / `community_type` (urban → urban_industrialized,
non-urban / rural → rural_non_industrialized), diet keys only for an exact vegan / vegetarian value (272 samples; 'Omnivore', 'MIND',
'Vegetarian but eat seafood' → nothing), `tribe` (the key states tribal membership → indigenous_community, tribe name as detail; the utility model agreed on
every value), `population` / `community` (33 values screened: study-arm codes such as AFCRO-121-003 and 'human' → nothing). `gut_lifestyle_map.parquet`
(158 distinct key × value pairs, 22 coded). Confidence 0.85.

| attr_key_norm | attr_value | code | method | n_samples |
|---|---|---|---|---|
| urban | urban | urban_industrialized | urban_rural_key | 858 |
| urban | non-urban | rural_non_industrialized | urban_rural_key | 498 |
| host_diet | Vegan | vegetarian_or_vegan | diet_exact | 171 |
| host_diet | Vegetarian | vegetarian_or_vegan | diet_exact | 41 |
| diet | Vegan | vegetarian_or_vegan | diet_exact | 33 |
| community_type | Rural | rural_non_industrialized | urban_rural_key | 23 |
| rural_urban_status | rural | rural_non_industrialized | urban_rural_key | 20 |
| rural_urban_status | urban | urban_industrialized | urban_rural_key | 20 |
| tribe | Warli | indigenous_community | tribe_key+utility_agrees | 16 |
| host_diet | vegan | vegetarian_or_vegan | diet_exact | 12 |
| tribe | Gondia | indigenous_community | tribe_key+utility_agrees | 12 |
| tribe | Kabui | indigenous_community | tribe_key+utility_agrees | 12 |
| tribe | Purigpa | indigenous_community | tribe_key+utility_agrees | 10 |
| tribe | Balti | indigenous_community | tribe_key+utility_agrees | 9 |
| tribe | Brokpa | indigenous_community | tribe_key+utility_agrees | 9 |
| tribe | Madia | indigenous_community | tribe_key+utility_agrees | 9 |
| tribe | Boto | indigenous_community | tribe_key+utility_agrees | 6 |
| diet | Vegetarian | vegetarian_or_vegan | diet_exact | 6 |
| host_diet | vegetarian | vegetarian_or_vegan | diet_exact | 4 |
| community_type | Urban | urban_industrialized | urban_rural_key | 4 |
| special_diet | vegetarian | vegetarian_or_vegan | diet_exact | 3 |
| diet | vegetarian | vegetarian_or_vegan | diet_exact | 2 |

### Confidence per field (determination rows)

| field_name | 0.6 | 0.7 | 0.75 | 0.8 | 0.85 | 0.9 |
|---|---|---|---|---|---|---|
| collection_date | 0 | 0 | 0 | 284 | 0 | 321688 |
| latitude | 0 | 13870 | 0 | 0 | 0 | 239781 |
| lifestyle | 0 | 0 | 0 | 0 | 1775 | 0 |
| lifestyle_detail | 0 | 0 | 0 | 0 | 1775 | 0 |
| location_locality | 0 | 0 | 3724 | 0 | 117190 | 0 |
| location_region | 124272 | 0 | 21024 | 0 | 47612 | 0 |
| location_site | 0 | 0 | 46 | 0 | 7047 | 0 |
| longitude | 0 | 13870 | 0 | 0 | 0 | 239781 |

## C. Assembly — pack-driven scope build (build/gut/: 2,837 studies, 579,252 samples, 3,015,622 current determinations, 103,793 route conflicts)

Existing fields are unchanged versus 1.11.0 (release-notes diff: Δ n = +0 for every 1.11.0 field; determination rows +1,153,739 = exactly the new-field rows).

### Coverage of the new fields over 579,252 samples

| field | samples with a value | share of 579,252 | studies |
|---|---|---|---|
| collection_date | 321972 | 55.6% | 1960 |
| collection_year | 321972 | 55.6% | 1960 |
| location_region | 192908 | 33.3% | 1280 |
| location_locality | 120914 | 20.9% | 921 |
| location_site | 7093 | 1.2% | 50 |
| detailed_location | 230095 | 39.7% | 1573 |
| latitude | 253651 | 43.8% | 1527 |
| longitude | 253651 | 43.8% | 1527 |
| lifestyle | 1775 | 0.3% | 14 |
| lifestyle_detail | 1775 | 0.3% | 14 |

### collection_year histogram (samples)

| collection_year | samples |
|---|---|
| 1990 | 2 |
| 1993 | 16 |
| 1994 | 8 |
| 1997 | 1 |
| 1998 | 2 |
| 2001 | 1 |
| 2002 | 8 |
| 2003 | 2 |
| 2004 | 624 |
| 2005 | 8 |
| 2006 | 17 |
| 2007 | 29 |
| 2008 | 1212 |
| 2009 | 697 |
| 2010 | 2860 |
| 2011 | 2546 |
| 2012 | 6653 |
| 2013 | 7949 |
| 2014 | 11801 |
| 2015 | 14761 |
| 2016 | 20832 |
| 2017 | 32966 |
| 2018 | 32325 |
| 2019 | 28794 |
| 2020 | 24244 |
| 2021 | 47977 |
| 2022 | 40787 |
| 2023 | 25269 |
| 2024 | 14033 |
| 2025 | 4901 |
| 2026 | 647 |

### Top 20 localities (text-derived only — no locality is reverse-geocoded)

| location_locality | samples |
|---|---|
| Beijing | 5436 |
| Boston | 5364 |
| Malmö | 4978 |
| San Diego | 4878 |
| Chicago | 3939 |
| Copenhagen | 3727 |
| Seoul | 2696 |
| San Francisco | 2659 |
| Shanghai | 2386 |
| Houston | 2303 |
| Singapore | 2116 |
| Philadelphia | 2021 |
| Copan | 1889 |
| Durham | 1791 |
| St. Louis | 1611 |
| Baltimore | 1574 |
| Hong Kong | 1542 |
| Boulder | 1536 |
| Hohhot | 1509 |
| Paris | 1380 |

Top 10 regions (text + reverse-geocoded): California 14,119, England 8,757, New York 6,709, Massachusetts 5,954, Uppsala 5,386, Pennsylvania 5,240, Illinois 5,120, Skane 5,072, Vaestra Goetaland 4,695, Ontario 4,589.

### Lifestyle code counts

| lifestyle | samples |
|---|---|
| urban_industrialized | 882 |
| rural_non_industrialized | 541 |
| vegetarian_or_vegan | 269 |
| indigenous_community | 83 |

Top lifestyle_detail values: {"urban": 878, "non-urban": 498, "Vegan": 204, "Vegetarian": 44, "Rural": 23, "rural": 20, "Warli": 16, "vegan": 12, "Kabui": 12, "Gondia": 12, "Purigpa": 10, "vegetarian": 9}.

### Conflicts — `gut_r1_newfields_conflicts.parquet` (203 rows)
A sample with two different values for one field from two keys keeps the higher-confidence, then the more specific (longer) value, then the
higher-priority key; the losers are logged with `winner_value`.

| field_name | n | example |
|---|---|---|
| lifestyle_detail | 3 | Vegetarian lost to vegetarian (biosample.attribute:host_diet) |
| location_locality | 54 | Chihuri lost to Chakandora (biosample.attribute:village_grouping) |
| location_region | 146 | Oregon lost to California (biosample.attribute:state) |

## Deviations and open points
* `config/models.yaml` has no `utility` role; `_utility_model()` tries `utility` and falls back to `screen` (the Haiku-class role) — resolved to `claude-haiku-4-5-20251001`.
  Adding `utility` to models.yaml is a one-line config change outside the files this task owns.
* Country bounding boxes: Natural Earth not available offline → GeoNames cities1000 nearest-place country (offline) used instead, as the task allows.
* Reverse geocoding restricted to `location_region` (see B); the task's permission covered locality too — declined for the quality reasons stated above.
* The location map was produced in one model pass; after the exonym-similarity rule was added the stored map was re-validated with the same validator
  (8 fields dropped, e.g. 'Mongolia: TUW province' → 'Tuvalu', 'Australia: WA' → 'Western Australia') without a second model pass.
* `config/version.txt` / `config/releases.yaml` still say 1.11.0 / R2026.11 — the release bump is the root's cut; the build here ran with
  `RELEASE_ID=R2026.12 VERSION=1.12.0` overrides. `audit/registry_schema.json` (marked frozen) was extended with the new table/columns because the
  DATA_DICTIONARY generator reads it. The site generator (`site_generator/`) is untouched.
* LLM usage: 35 utility-model calls, 180,040 input + 77,934 output = 257,974 tokens (ceiling 1.5 M).

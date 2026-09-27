# REGISTRY_S2_PAPERS — S2 pilot B: papers and authors for the `human_all` registry studies

*Pilot of SCALE_UP_PLAN phase S2 (registry tier: papers + authors). Input `registry_human_all_studies.parquet` (R2026.4, 4,576 studies). Deterministic harvest; no LLM calls. Cache-through via `harvest_lib` (per-host token bucket: EBI 4 req/s, NCBI 2.5 req/s, 3 workers).*

## 1. Scope and coverage

| quantity | value |
|---|---:|
| studies in input | 4,576 |
| studies already in the curated infant catalog (`in_infant_catalog == include`) — left out, papers/authors live in the curated package | 359 |
| studies processed (`in_infant_catalog != include`: exclude / uncertain / not_screened) | 4,217 |
| Europe PMC study queries answered HTTP 200 | 4,217 (0 failures) |
| BioProject records found in NCBI | 4,214 of 4,217 (99.9%); 0 batch failures |
| network requests (EBI + NCBI, all stages) | 9,569 (cached re-reads 4, errors 0) |
| harvest wall time | 2,872 s (48 min) |

## 2. Papers

| quantity | value |
|---|---:|
| paper × study link rows (`registry_study_papers.parquet`) | 6,398 |
| distinct papers | 4,064 |
| studies with ≥ 1 linked paper (any source) | 2,676 (63.5%) |
| studies with ≥ 1 Europe PMC accession mention | 2,589 (61.4%) |
| studies with ≥ 1 `own_data` link (deterministic) | 2,336 (55.4%) |
| studies with a BioProject-declared publication | 384 (9.1%) |
| open-access share of linked papers (Europe PMC `isOpenAccess`, 6,386 rows with a value) | 90.1% |
| rows with a PMID / with a DOI / with a PMCID | 6,212 / 6,378 / 6,136 |
| studies whose Europe PMC hit list exceeded the 300-result cap | 0 (max hitCount 106) |
| studies whose returned results were fewer than `hitCount` (Europe PMC count/result mismatch) | 1 |

### 2.1 Papers per linked study

| papers per study | studies |
|---|---:|
| 1 | 1,801 |
| 2 | 403 |
| 3 | 177 |
| 4-5 | 128 |
| 6-10 | 94 |
| >10 | 73 |
| **median / mean / max** | 1 / 2.39 / 106 |

### 2.2 Source, match field, match accession

| source | rows |
|---|---:|
| `europepmc_mention` | 5,926 |
| `bioproject_xml` | 239 |
| `both` | 233 |

| match_field | rows |
|---|---:|
| `fulltext_only` | 6,111 |
| `bioproject_declared` | 239 |
| `abstract_or_title` | 48 |

| match_accession | rows |
|---|---:|
| primary (PRJ) | 5,701 |
| secondary (SRP/ERP/DRP) | 697 |

`match_field`: `abstract_or_title` = accession found by an `ABSTRACT:`/`TITLE:`-qualified Europe PMC query; `fulltext_only` = found only by the unrestricted query (Europe PMC indexes accession mentions in open-access full text); `bioproject_declared` = publication id deposited in the BioProject XML, no Europe PMC mention found. `match_accession` is resolved by a second query on the secondary accession alone (stage 5); for `bioproject_declared` rows it is the primary accession by construction.

### 2.3 Deterministic link classification (link_papers.classify adapted to the registry tier)

At the registry tier no full-text section labels are mined, so the curated rules (`det_data_availability`, `det_single_mention`) are replaced by: `det_bioproject_declared` (submitter-declared publication, own_data 0.9) · `det_single_mention_abstract` (paper mentions exactly one registry study, in abstract/title; own_data 0.75) · `det_single_mention_fulltext` (exactly one registry study, full text only; own_data 0.6) · everything else `unsure`, `contest_reason = multi_study` (a paper mentioning ≥ 2 processed studies is typically a re-analysis / meta-analysis). `n_registry_studies` counts processed studies only (the 359 curated studies are not in the denominator).

| relation | rows |
|---|---:|
| `own_data` | 3,371 |
| `unsure` | 3,027 |

| method | rows |
|---|---:|
| `none (unsure)` | 3,027 |
| `det_single_mention_fulltext` | 2,867 |
| `det_bioproject_declared` | 472 |
| `det_single_mention_abstract` | 32 |

Share of link rows whose paper mentions ≥ 2 processed studies: 48.2% (max 29 studies for one paper).

### 2.4 Publication year of linked papers

| year | rows |
|---|---:|
| 2010 | 1 |
| 2011 | 1 |
| 2012 | 9 |
| 2013 | 19 |
| 2014 | 40 |
| 2015 | 47 |
| 2016 | 75 |
| 2017 | 119 |
| 2018 | 144 |
| 2019 | 240 |
| 2020 | 394 |
| 2021 | 654 |
| 2022 | 876 |
| 2023 | 839 |
| 2024 | 961 |
| 2025 | 1,145 |
| 2026 | 827 |
| < 2010 | 5 |

## 3. BioProject records (`registry_bioproject_records.parquet`, one row per processed study)

| quantity | value |
|---|---:|
| rows | 4,217 |
| found in NCBI BioProject | 4,214 |
| with organisation | 4,214 |
| with submitter owner (role=owner) | 4,213 |
| with ≥ 1 declared publication | 384 |
| with declared PMID(s) / DOI-only | 305 / 79 |
| with `registration_date` / `submitted` date | 239 / 4,181 |
| with data type | 4,210 |

| data_types (top) | studies |
|---|---:|
| raw sequence reads | 2,450 |
| Other | 1,041 |
| metagenome | 358 |
| Genome sequencing and assembly | 84 |
| Genome sequencing | 70 |
| Metagenome | 50 |
| genome sequencing and assembly | 32 |
| genome sequencing | 26 |

| organisation (top 12, `;`-split) | studies |
|---|---:|
| Wellcome Sanger Institute | 51 |
| Institut National pour la Recherche Agronomique (FRANCE) | 35 |
| University of California San Diego Microbiome Initiative | 34 |
| National Institute for Viral Disease Control and Prevention, China CDC | 32 |
| Stanford University | 29 |
| Inner Mongolia Agricultural University | 27 |
| European Molecular Biology Laboratory | 26 |
| Jiangsu University | 24 |
| HUG | 23 |
| Quadram Institute Bioscience | 21 |
| Genoscope | 20 |
| Mayo Clinic | 20 |

## 4. Authors (`registry_authors.parquet`, one row per study × paper × author)

Author harvest capped at the first 5 linked papers per study (order: BioProject-declared + mentioned, then abstract matches, then Europe PMC rank). Shape follows the curated `authors.parquet` (`author_display`, `author_surname`, `author_initials`, `is_group`, `source`, `pmid`, `position`, `n_authors`, `is_first`, `is_last`, `paper_relation`, `link_method`, `author_key`) plus `author_full_name`, `affiliation`, `orcid` from Europe PMC `resultType=core`. No disambiguation across name variants.

| quantity | value |
|---|---:|
| author rows | 52,110 |
| studies with ≥ 1 author row | 2,676 (63.5%) |
| study × paper pairs with authors | 4,529 |
| distinct `author_key` (surname + initials) | 21,881 |
| rows with ORCID / distinct ORCIDs | 18,527 (35.6%) / 9,583 |
| rows with affiliation | 50,642 (97.2%) |
| group / consortium authors | 175 |
| source `linked_paper` | 52,039 |
| source `bioproject_publication` | 71 |

## 5. Link rate by primary body-site scope

| body_site_primary | studies | with paper | link rate | with own_data paper | own_data rate | BioProject-declared |
|---|---:|---:|---:|---:|---:|---:|
| gut_stool | 2,278 | 1,488 | 65.3% | 1,269 | 55.7% | 237 |
| unknown_site | 399 | 201 | 50.4% | 184 | 46.1% | 13 |
| respiratory_lower | 344 | 224 | 65.1% | 192 | 55.8% | 22 |
| blood_tissue | 318 | 197 | 61.9% | 182 | 57.2% | 31 |
| oral | 305 | 200 | 65.6% | 173 | 56.7% | 29 |
| vaginal_urogenital | 148 | 93 | 62.8% | 86 | 58.1% | 7 |
| skin | 141 | 83 | 58.9% | 77 | 54.6% | 20 |
| multi_site | 93 | 64 | 68.8% | 56 | 60.2% | 11 |
| other_site | 76 | 51 | 67.1% | 48 | 63.2% | 6 |
| nasal_nasopharyngeal | 66 | 41 | 62.1% | 40 | 60.6% | 6 |
| eye_ear | 42 | 29 | 69.0% | 25 | 59.5% | 2 |
| milk | 7 | 5 | 71.4% | 4 | 57.1% | 0 |

## 6. Failures and timeouts

* Europe PMC: 0 study queries without HTTP 200 (stage 1); 0 failed requests over all stages after `harvest_lib` retries (429/5xx back-off).
* NCBI BioProject: 0 failed esearch/efetch batches; 3 processed studies have no NCBI BioProject record (PRJEB108618, PRJEB79367, PRJNA448876).
* No study reached the 300-result cap; 16 link rows belong to 1 study whose result list was one shorter than its `hitCount` (PRJEB12123; `epmc_hits_capped` flags it).

## 7. Deviations and caveats

* The task text counts 389 curated studies; the input table carries 359 rows with `in_infant_catalog == include` (the difference cannot be resolved from this input). Every row with `in_infant_catalog != include` was processed: 4,217 studies, including 31 `uncertain` and 149 `not_screened`.
* Paper links are accession-mention links without section mining (no JATS full text or supplementary ZIP fetched at the registry tier); `relation`/`confidence` therefore use the reduced rule set of §2.3 and are weaker than the curated `study_paper_links` (`det_data_availability` needs section labels). Rows with `relation = unsure` need the curated-tier linker (or a curator) before use as own-data evidence.
* Europe PMC full-text indexing covers open-access articles only: a closed-access paper that cites the accession only in its body is invisible here (its abstract is still searched). Link rates are lower bounds.
* Authors are harvested for at most 5 linked papers per study (task cap); papers of `unsure` relation are included in that cap when fewer than 5 higher-ranked links exist, so `paper_relation` must be checked before attributing a study to an author.
* BioProject-declared publications without a Europe PMC record (`source = bioproject_xml`) carry the title/journal/year deposited by the submitter and no `is_open_access` value unless a core record was resolved by PMID or DOI.
* Registry-tier tables carry no bitemporal columns yet (`release_added` etc. are appended by `make registry-build` per config/releases.yaml); the 359 curated studies are absent by design.

## 8. Files

* `registry_study_papers.parquet` — one row per (study_accession, paper_id); `paper_id` = Europe PMC `SRC:ID` (PMID for MED) or `doi:<doi>` for declared DOIs without a record; columns compatible with `study_paper_links` (`study_accession`, `paper_id`, `pmid`, `pmcid`, `doi`, `title`) + `journal`, `year`, `pub_type`, `is_open_access`, `in_epmc_fulltext`, `source`, `match_field`, `match_accession`, `bioproject_declared`, `n_registry_studies`, `relation`, `method`, `confidence`, `contested`, `contest_reason`, `epmc_rank`, `epmc_hit_count`, `epmc_hits_capped`, `body_site_primary`.
* `registry_bioproject_records.parquet` — one row per processed study (`found_in_ncbi`, `bioproject_uid`, `organisation`, `submitter_owner`, `organizations_json`, `n_publications`, `publication_pmids`, `publication_dois`, `publications_json`, `grants_json`, `external_links_json`, `registration_date`, `submitted`, `last_update`, `submission_access`, `data_types`, `target_material`, `target_capture`, `target_sample_scope`, `method_type`, `relevance_medical`, `body_site_primary`).
* `registry_authors.parquet` — one row per study × paper × author (see §4).
* `registry_s2_link_rate_by_site.csv` — §5 table.
* `harvest_s2b.py`, `assemble_s2b.py`, `report_s2b.py` — the pilot code (candidates for `src/catalog/registry/`).

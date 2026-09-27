# Registry universe enumeration (S1a) -- ENUMERATION_REGISTRY_REPORT
Generated 2026-09-27 07:04 UTC; runtime 471s; deterministic (no LLM calls); all HTTP cache-through via harvest_lib. No date window, no taxon frame.

## Slices and completeness (registry_universe_audit.csv)
| slice | partition | ena_count | rows_pulled | complete | seconds |
|---|---|---|---|---|---|
| S1 | y2010 | 1862 | 1862 | True | 0.0 |
| S1 | y2011 | 1045 | 1045 | True | 0.0 |
| S1 | y2012 | 7645 | 7645 | True | 0.1 |
| S1 | y2013 | 6019 | 6019 | True | 0.0 |
| S1 | y2014 | 11247 | 11247 | True | 0.1 |
| S1 | y2015 | 24668 | 24668 | True | 0.2 |
| S1 | y2016 | 18494 | 18494 | True | 0.1 |
| S1 | y2017 | 35544 | 35544 | True | 0.3 |
| S1 | y2018 | 53985 | 53985 | True | 0.4 |
| S1 | y2019 | 87954 | 87954 | True | 0.7 |
| S1 | y2020 | 87741 | 87741 | True | 0.7 |
| S1 | y2021 | 99071 | 99071 | True | 0.8 |
| S1 | y2022 | 111886 | 111886 | True | 0.9 |
| S1 | y2023q1 | 44101 | 44101 | True | 0.3 |
| S1 | y2023q2 | 44844 | 44844 | True | 0.3 |
| S1 | y2023q3 | 36324 | 36324 | True | 0.3 |
| S1 | y2023q4 | 36046 | 36046 | True | 0.3 |
| S1 | y2024q1 | 53477 | 53477 | True | 0.4 |
| S1 | y2024q2 | 41424 | 41424 | True | 0.3 |
| S1 | y2024q3 | 48802 | 48802 | True | 0.4 |
| S1 | y2024q4 | 75871 | 75871 | True | 0.6 |
| S1 | y2025q1 | 60575 | 60575 | True | 0.5 |
| S1 | y2025q2 | 66581 | 66581 | True | 0.6 |
| S1 | y2025q3 | 54876 | 54876 | True | 0.4 |
| S1 | y2025q4 | 75675 | 75675 | True | 0.6 |
| S1 | y2026q1 | 79923 | 79923 | True | 0.6 |
| S1 | y2026q2 | 103156 | 103156 | True | 0.8 |
| S1 | y2026q3 | 66596 | 66596 | True | 0.5 |
| S1 | y2026q4 | 0 | 0 | True | 0.0 |
| S1 | fill_missing_from_index | 29952 | 29952 | True | 0.0 |
| S1 | TOTAL | 1465384 | 1465384 | True | 11.2 |
| S2 | all | 62089 | 62089 | True | 0.5 |
| S2 | TOTAL | 62089 | 62089 | True | 0.5 |
| S3 | all | 457755 | 457755 | True | 46.4 |
| S3 | TOTAL | 457755 | 457755 | True | 46.4 |

S4 (library_source=METATRANSCRIPTOMIC) is out of scope and was not pulled. S3 pulls every METAGENOMIC x OTHER/Targeted-Capture/WGA run (no taxon restriction), OTHER-source runs only with a human host/taxon signal, and GENOMIC-source runs only on the 21 human-metagenome taxa; GENOMIC x tax_eq(9606) (human genome sequencing, 1.19M runs on 2026-09-27) and GENOMIC x host_tax_id=9606 (bacterial isolate genomes, 70k runs) are excluded by design.

## Runs
* registry_runs.parquet: **1,980,623** unique runs / **54,361** studies; columns = 45 read_run PULL_FIELDS + found_by.
* runs found by slice: S1 1,464,800, S3 453,742, S2 62,081
* runs with blank tax_id: 110,722; studies with blank tax_id on every run: 1,887; on >=1 run: 2,321
* studies without an ENA study record (title from read_run): 132

## Human-signal rule (resweep_universe.human_signal verbatim + taxon-name rule)
* human_signal True: **6,679** -- rule A 3,895, B 2,575, C 209
* taxon-name rule (scientific_name 'human ...' or host_tax_id 9606 on >=1 run): 4,764 (adds 37 not caught by A/B/C)
* ambiguous (human terms, animal/env score >= human score): 1,124

## Candidate classes
| candidate_class | studies | runs |
|---|---|---|
| nosignal_new | 42973 | 567177 |
| prior_human | 5856 | 1051634 |
| prior_nonhuman | 3676 | 188718 |
| signal_human_new | 1095 | 88516 |
| ambiguous_new | 761 | 84578 |

### by slice (found_by)
| found_by | ambiguous_new | nosignal_new | prior_human | prior_nonhuman | signal_human_new | studies |
|---|---|---|---|---|---|---|
| S1 | 469 | 27862 | 4630 | 2942 | 1 | 35904 |
| S1;S2 | 0 | 0 | 24 | 4 | 0 | 28 |
| S1;S2;S3 | 0 | 0 | 2 | 0 | 0 | 2 |
| S1;S3 | 13 | 183 | 126 | 35 | 3 | 360 |
| S2 | 0 | 0 | 194 | 92 | 36 | 322 |
| S2;S3 | 0 | 0 | 4 | 2 | 0 | 6 |
| S3 | 279 | 14928 | 876 | 601 | 1055 | 17739 |

## Infant universe re-found
* infant universe (universe_studies_all.parquet): 9,581 studies; re-found in the registry universe: **9,532**; missed: **49**
| study_accession | triage_verdict | reason_code | universe_slice | study_title | n_runs |
|---|---|---|---|---|---|
| PRJNA897707 | exclude | assay_isolate_genome | growth_enum_v3_delta_2026-09-24 | Lactiplantibacillus plantarum strain:MC5 | isolate:Traditional fermented yak milk | breed:Bacteria | cultivar:Lactic acid bacteria Genome sequencing and assembly | 3 |
| PRJEB3145 | exclude | assay_isolate_genome | growth_cngb_mirror_2026-09-24 | Escherichia coli isolates from infants in Trondheim | 16 |
| PRJEB43051 | exclude | host_environmental | growth_cngb_mirror_2026-09-24 | Nuclear and mtDNA sequences of Arma Veirana Mesolithic infant burial, Italy | 8 |
| PRJNA16209 | exclude | assay_rna | growth_cngb_mirror_2026-09-24 | Metagenome sequencing of RNA viruses in human feces | 3 |
| PRJNA600283 | exclude | assay_amplicon | growth_cngb_mirror_2026-09-24 | Meconium samples | 166 |
| PRJNA797011 | exclude | assay_rna | growth_cngb_mirror_2026-09-24 | T cell receptor repertoire in premature infants | 40 |
| PRJDB19503 | exclude | assay_amplicon | growth_kona_mirror_2026-09-24 | Stool 16S rRNA amplicon sequencing of Korean Crohn's disease and ulcerative colitis patients (KAP230691) | 357 |
| PRJDB39894 | exclude | assay_other_nonshotgun | growth_kona_mirror_2026-09-24 | Constructions and application technology development of the infra- system for Korean gut microbiome (KAP230597) | 728 |
| PRJNA1119695 | exclude | assay_amplicon | growth_kona_mirror_2026-09-24 | Microbiome information of healthy controls and schizophrenia patients | 14 |
| PRJNA1175752 | exclude | site_excluded | growth_kona_mirror_2026-09-24 | Skin microbiota in atopic dermatitis | 94 |
| PRJNA31013 | exclude | assay_isolate_genome | growth_biosample_attribute_sweep_2026-09-24 | reference genome for the Human Microbiome Project | 1 |
| PRJNA1077459 | exclude | assay_isolate_genome | growth_biosample_attribute_sweep_2026-09-24 | Trio Whole Exome Sequencing of Rare Disease | 3 |
| PRJNA1430382 | exclude | assay_isolate_genome | growth_biosample_attribute_sweep_2026-09-24 | Genome sequence from Bifidobacterium longum subsp. infantis E16 | 1 |
| PRJNA19663 | exclude | assay_isolate_genome | growth_biosample_attribute_sweep_2026-09-24 | Reference genome for the Human Microbiome Project | 2 |
| PRJNA1270758 | exclude | assay_isolate_genome | growth_biosample_attribute_sweep_2026-09-24 | WES data from a Chinese family with hereditary hyperferritinemia-cataract syndrome (HHCS) and axial elongation | 7 |
| PRJNA1191226 | exclude | assay_isolate_genome | growth_biosample_attribute_sweep_2026-09-24 | Enterococcus plasmid transfer study using human gut models | 23 |
| PRJNA1389337 | exclude | host_environmental | growth_biosample_attribute_sweep_2026-09-24 | Multistate Infant Botulism Outbreak -- CA | 4 |
| PRJNA1145565 | exclude | assay_isolate_genome | growth_biosample_attribute_sweep_2026-09-24 | WES of Taiwain Children with Enterovirus (EV) Infections | 25 |
| PRJEB9867 | exclude | assay_isolate_genome | growth_biosample_attribute_sweep_2026-09-24 | Molecular typing of Toxic shock syndrome toxin-1- and Enterotoxin A-producing methicillin-sensitive Staphylococcus aureus isolates from an outbreak in a neonatal intensive care unit | 24 |
| PRJEB24865 | exclude | assay_isolate_genome | growth_biosample_attribute_sweep_2026-09-24 | Exomes of human leukemic JMML (Juvenile MyeloMonocytic Leukemia) cells and paired fibroblasts (germilne controls) when available | 28 |
| PRJNA1314725 | exclude | host_environmental | growth_biosample_attribute_sweep_2026-09-24 | Evidence for improved DNA repair in long-lived bowhead whale | 159 |
| PRJNA1010893 | uncertain | nan | growth_biosample_attribute_sweep_2026-09-24 | MILK-Omics: Systems Biology of Human Milk and its Links to Maternal and Infant Health | 595 |
| PRJNA273428 | exclude | assay_isolate_genome | growth_biosample_attribute_sweep_2026-09-24 | Clostridium botulinum Genome sequencing | 4 |
| PRJNA1142219 | exclude | assay_isolate_genome | growth_biosample_attribute_sweep_2026-09-24 | Lacticaseibacillus paracasei strain:MYA5 | isolate:Sejong Oh Genome sequencing | 2 |
| PRJNA1334008 | exclude | host_environmental | growth_biosample_attribute_sweep_2026-09-24 | Personalized viral genomic investigation of herpes simplex virus 1 perinatal viremic transmission with dual fatality | 3 |
| PRJDB3402 | exclude | assay_isolate_genome | growth_biosample_attribute_sweep_2026-09-24 | whole genome sequence, Clostridium botulinum type B strain 111 | 4 |
| PRJEB39293 | exclude | assay_isolate_genome | growth_biosample_attribute_sweep_2026-09-24 | Maternal and neonatal rectal carriage of beta-lactamases from low- and middle-income countries: prevalence, risk factors and genomes (part of the BARNARDS study). | 422 |
| PRJNA213036 | exclude | assay_isolate_genome | growth_biosample_attribute_sweep_2026-09-24 | Cronobacter sakazakii NCIMB 8272 Genome sequencing and assembly | 1 |
| PRJNA203137 | exclude | assay_isolate_genome | growth_biosample_attribute_sweep_2026-09-24 | Lactobacillus paragasseri K7 strain:K7 Genome sequencing and assembly | 1 |
| PRJNA801086 | exclude | host_environmental | growth_biosample_attribute_sweep_2026-09-24 | Clinical and molecular genetic diagnosis of primary ciliary dyskinesia | 3 |
| PRJNA772001 | exclude | assay_isolate_genome | growth_biosample_attribute_sweep_2026-09-24 | Vibrio spp. isolated from Canadian-harvested fresh mollusks (2014-2018) | 12 |
| PRJNA669437 | exclude | host_environmental | growth_biosample_attribute_sweep_2026-09-24 | Changes of microorganism during fermentation of Hongqu rice | 16 |
| PRJNA512395 | exclude | assay_isolate_genome | growth_biosample_attribute_sweep_2026-09-24 | Genomic investigation reveals contaminated detergent as the source of an ESBL-producing Klebsiella oxytoca outbreak in a neonatal unit | 28 |
| PRJNA450302 | exclude | assay_isolate_genome | growth_biosample_attribute_sweep_2026-09-24 | Bordetella pertussis Genome sequencing and assembly | 56 |
| PRJNA786382 | exclude | host_environmental | growth_biosample_attribute_sweep_2026-09-24 | Comprehensive genetic diagnosis of tandem repeat expansion disorders with programmable targeted nanopore sequencing | 114 |
| PRJNA847410 | exclude | assay_isolate_genome | growth_biosample_attribute_sweep_2026-09-24 | Enterobacteriaceae strains isolated from newborns in a Chinese hospital | 128 |
| PRJNA912682 | exclude | assay_isolate_genome | growth_biosample_attribute_sweep_2026-09-24 | Epidemiology and impact of emerging Campylobacter species isolated from humans and animals in Loreto Department Peru: Genome sequencing and assembly | 223 |
| PRJNA799072 | exclude | assay_isolate_genome | growth_biosample_attribute_sweep_2026-09-24 | Whole genome sequencing of RPE1 LATS1/2-double knockout cells implanted into mice. | 5 |
| PRJNA838803 | exclude | assay_isolate_genome | growth_biosample_attribute_sweep_2026-09-24 | Lacticaseibacillus paracasei strain:D401 Genome sequencing | 1 |
| PRJNA759433 | exclude | assay_isolate_genome | growth_biosample_attribute_sweep_2026-09-24 | Clostridium botulinum Genome sequencing and assembly of clinical and food isolates from 1995 infant botulism investigation | 2 |
| PRJNA407835 | exclude | assay_other_nonshotgun | growth_biosample_attribute_sweep_2026-09-24 | Homo sapiens Raw sequence reads | 3 |
| PRJEB13965 | exclude | host_environmental | growth_reanalysis_raw_link_2026-09-24 | Ecoli data | 1 |
| PRJEB43160 | exclude | host_environmental | growth_reanalysis_raw_link_2026-09-24 | This study deals with 6 metagenomes of modified Winogradsky columns, enriched at 24 °C and 28°C. Furthermore three enrichment cultures are analysed, which are a mixed consortia of algae and bacteria. | 9 |
| PRJNA504944 | exclude | site_excluded | growth_reanalysis_raw_link_2026-09-24 | Airway bacteria and P. aeruginosa pathogens under antibiotic therapy | 68 |
| PRJEB31185 | exclude | assay_isolate_genome | growth_reanalysis_raw_link_2026-09-24 | Metagenome sequencing of modern dental calculus | 10 |
| PRJEB26427 | exclude | host_environmental | growth_reanalysis_raw_link_2026-09-24 | Understanding the microbial basis of body odor in teenagers and kids | 179 |
| PRJEB13962 | exclude | host_environmental | growth_reanalysis_raw_link_2026-09-24 | the Ecoli fastq file | 2 |
| PRJNA884026 | exclude | host_environmental | growth_reanalysis_raw_link_2026-09-24 | Metagenomic investigation of lake Issyk-Kul, Kyrgyzstan | 50 |
| PRJNA61745 | include | nan | growth_reanalysis_raw_link_2026-09-24 | Strain-resolved community genomic analysis of gut microbial colonization in a premature infant | 43 |

## BioSample index
* registry_biosample_index.parquet: 1,033,506 (sample, secondary sample, study) rows across 7,712 human-candidate studies (prior_human + signal_human_new + ambiguous_new)

## Files
* registry_runs.parquet -- every run of the registry universe (working_data artifact)
* registry_universe_studies.parquet -- one row per study (frozen universe columns, summaries, rule, infant join, candidate_class)
* registry_biosample_index.parquet -- distinct BioSamples of the human-candidate studies
* registry_universe_audit.csv -- per-slice / per-partition ENA count vs rows pulled
* registry_study_meta.parquet -- ENA study records (title, description, center_name)

## Log
```
# registry enumeration  (2026-09-27 06:56 UTC) slices=['S1', 'S2', 'S3']
verify_taxa: 21 human-metagenome taxids match ENA scientific_name
[S1 shotgun_frame_free] ENA count 1,465,384
  [S1] index: 1,465,384 run accessions 1s
  [S1:y2010] rows=1,862 OK 0s
  [S1:y2011] rows=1,045 OK 0s
  [S1:y2012] rows=7,645 OK 0s
  [S1:y2013] rows=6,019 OK 0s
  [S1:y2014] rows=11,247 OK 0s
  [S1:y2015] rows=24,668 OK 0s
  [S1:y2016] rows=18,494 OK 0s
  [S1:y2017] rows=35,544 OK 0s
  [S1:y2018] rows=53,985 OK 0s
  [S1:y2019] rows=87,954 OK 1s
  [S1:y2020] rows=87,741 OK 1s
  [S1:y2021] rows=99,071 OK 1s
  [S1:y2022] rows=111,886 OK 1s
  [S1:y2023q1] rows=44,101 OK 0s
  [S1:y2023q2] rows=44,844 OK 0s
  [S1:y2023q3] rows=36,324 OK 0s
  [S1:y2023q4] rows=36,046 OK 0s
  [S1:y2024q1] rows=53,477 OK 0s
  [S1:y2024q2] rows=41,424 OK 0s
  [S1:y2024q3] rows=48,802 OK 0s
  [S1:y2024q4] rows=75,871 OK 1s
  [S1:y2025q1] rows=60,575 OK 0s
  [S1:y2025q2] rows=66,581 OK 1s
  [S1:y2025q3] rows=54,876 OK 0s
  [S1:y2025q4] rows=75,675 OK 1s
  [S1:y2026q1] rows=79,923 OK 1s
  [S1:y2026q2] rows=103,156 OK 1s
  [S1:y2026q3] rows=66,596 OK 0s
  [S1:y2026q4] expected 0 -- skipped
  [S1:fill] accession fill: 29,952/29,952 runs
[S1] union 1,465,384 runs vs ENA count 1,465,384 / index 1,465,384 (missing after fill 0, extra 0)
[S2 misfiled_genomic_human_taxa] ENA count 62,089
  [S2] index: 62,089 run accessions 0s
  [S2] rows=62,089 OK 0s
[S2] union 62,089 runs vs ENA count 62,089 / index 62,089 (missing after fill 0, extra 0)
[S3 adjudication_other_tc_wga] ENA count 457,755
  [S3] index: 457,755 run accessions 71s
  [S3] rows=457,755 OK 46s
[S3] union 457,755 runs vs ENA count 457,755 / index 457,755 (missing after fill 0, extra 0)
registry_runs: 1,985,228 rows -> 1,980,623 unique runs / 54,361 studies (4605 rows with empty study_accession dropped)
loaded 40,231 study records from build/registry3/registry_study_meta.parquet
fetching study records for 15,227 new studies
study metadata: 15,095/15,227 requested studies have an ENA study record (132 without -> title from read_run; 21 unrequested rows returned) [762 calls, 192s]
aggregated 54,361 studies from 1,980,623 runs in 31s
human-signal rule on 54,361 studies in 97s: signal 6,679 (A 3,895 B 2,575 C 209), ambiguous 1,124, taxon-name rule only 37
candidate classes: {'nosignal_new': 42973, 'prior_human': 5856, 'prior_nonhuman': 3676, 'signal_human_new': 1095, 'ambiguous_new': 761}
infant universe re-found 9,532/9,581; biosample index 1,033,506 rows
```

## Miss analysis (49 infant-universe studies not re-found)
All 49 misses are deposits with **no run filed as METAGENOMIC x WGS/WXS, no METAGENOMIC x OTHER/Targeted-Capture/WGA run, and no GENOMIC run on a human-metagenome taxon** -- they entered the infant universe through channels the registry universe does not use (isolate-genome side table, literature raw-data links, BioSample attribute sweep). Filing patterns (library_source/library_strategy over the study's runs, ENA 2026-09-27): GENOMIC/WGS 30, GENOMIC/WXS 6, GENOMIC/WGS;METAGENOMIC/AMPLICON 2, GENOMIC/OTHER;GENOMIC/WGS 1, GENOMIC/OTHER;GENOMIC/Targeted-Capture 1, GENOMIC/OTHER 1, TRANSCRIPTOMIC/OTHER 1, METAGENOMIC/CLONEEND 1, GENOMIC/CLONEEND 1, GENOMIC/RNA-Seq 1, GENOMIC/AMPLICON;TRANSCRIPTOMIC/RNA-Seq 1, GENOMIC/AMPLICON;GENOMIC/WGS;TRANSCRIPTOMIC/RNA-Seq 1, GENOMIC/WGS;TRANSCRIPTOMIC/RNA-Seq 1, GENOMIC/WGA 1.
* 47 are infant-universe **excludes** (assay_isolate_genome 26, host_environmental 11, assay_amplicon 3, assay_other_nonshotgun 2, assay_rna 2, site_excluded 2, blank 2 -- from registry_infant_universe_misses.csv); none is a shotgun metagenome by the registry's assay definition.
* PRJNA61745 (**include**, growth_reanalysis_raw_link_2026-09-24): 4 runs filed GENOMIC/WGS under taxid 150489 'uncultured bacteria (human infant) ensemble' + 39 METAGENOMIC/AMPLICON runs (2011 deposit); it stays in the infant catalog through its literature link and is not reachable by any ENA library filter -- carry it into registry_studies from the infant catalog tables (scope_memberships=infant_gut).
* PRJNA1010893 (**uncertain**, growth_biosample_attribute_sweep_2026-09-24): 251 GENOMIC/WGS + 344 TRANSCRIPTOMIC/RNA-Seq runs filed under tax_id 9606 'Homo sapiens' (host-genome filing); reachable only through the BioSample-attribute sweep (SCALE_UP_PLAN §3 lists that sweep as the second enumeration channel; it is not part of S1a).
The first S3 formulation (taxon-restricted OTHER/TC/WGA) missed 467 infant-universe studies (339 METAGENOMIC/OTHER under generic 'metagenome'/virome taxa, 3 of them included cohorts); widening S3 to every METAGENOMIC x OTHER/TC/WGA run (+246,741 runs) recovered 418 of them and is the shipped definition.

## Column dictionary (registry_universe_studies.parquet)
Frozen universe columns: study_accession, secondary_study_accession, study_title, description_short (<=300 chars), center_name, first_public_min/max, n_runs, n_samples (secondary_sample_accession), n_biosamples (sample_accession), library_strategies/sources/selections/layouts (';' distinct), instrument_platforms, instrument_models_top and scientific_names_top ('value(count)' top-5), tax_ids, host_tax_ids, n_runs_host_9606, n_runs_nonhuman_host, n_runs_blank_tax_id, target_genes, n_target_gene, median_base_count, median_read_count, median_nominal_length, median_read_len_proxy (base_count/read_count), library_name_stems_top (digits->'#', first 12 chars).
Rule columns: human_signal (bool), human_signal_rule (A|B|C|none), ambiguous, taxon_name_rule, human_signal_any, human_specific_score, site_score, animal_score, site_terms, hspec_terms, animal_terms, taxon_name_human, taxon_nonhuman_species, n_runs_human_host, n_runs_hspec, n_runs_site, n_runs_animal, human_signal_reason.
Infant join: in_infant_catalog (include|exclude|uncertain|not_screened), infant_reason_code, infant_body_site_call, infant_universe_slice, infant_screened.
Classification input: candidate_class (prior_nonhuman|prior_human|signal_human_new|ambiguous_new|nosignal_new), universe_slice, found_by, has_ena_study_record, description (full), top_<field> json {value: count} top-10 for sample_title, host_scientific_name, host_body_site, isolation_source, environmental_medium, dev_stage, age, host_sex, tissue, host, environment_material, country, checklist (host_sex/tissue are not ENA read_run fields and are empty placeholders until the BioSample attribute harvest).
Bitemporal columns (release_added, release_retired, package_added) are appended by catalog.release.bitemporal at package build; the frozen registry_studies classification columns (host_human, assay, body_sites, life_stages, ...) are filled by the S1b classification stage.

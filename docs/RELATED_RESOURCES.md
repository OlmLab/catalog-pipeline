# Related resources — human microbiome metadata efforts and what Microbiome Repo could ingest
*Generated from `config/sources.yaml` (reviewed 2026-09-28); the same content is the site's Sources page. Web survey of 2026-09-28 (curatedMetagenomicData 3, GMrepo v3, MicrobeAtlas, Human Microbiome Compendium, African Human Microbiome Portal, Meta2DB, PRIME, EMBERS, HumanMetagenomeDB, mBodyMap, MicrobiomeDB, BugSigDB, MGnify, HMP) plus resources known from the literature.*

## Assessment table

| resource | scope | size | offers | join key | licence | ingestion |
|---|---|---|---|---|---|---|
| [curatedMetagenomicData 3 (cMD 3)](https://waldronlab.io/curatedMetagenomicData/) | human shotgun metagenomes, all body sites; manually curated per-sample metadata | > 22,000 samples, 94 studies, 42 countries (cMD 3) | Per-sample curated age, sex, BMI, country, disease, antibiotics and study condition; MetaPhlAn/HUMAnN profiles; NCBI accessions per sample. | sample_metadata NCBI_accession (SRR/ERR run ids, ';'-separated) → registry runs → BioSample; study_name → PMID / BioProject. | Artistic-2.0; metadata redistributable with attribution | **candidate_high** |
| [GMrepo v3](https://gmrepo.humangut.info/) | human gut, 16S and shotgun; phenotype-centred curation | 890 projects, 118,965 runs/samples (87,048 16S · 31,917 WGS), 302 diseases (v3) | Per-run curated phenotype (MeSH disease), age, sex, BMI, country, health status; project-level markers; RESTful API and downloads. | run accession (SRR/ERR/DRR) and project id (PRJNA…) → registry runs / studies. | Check the site's terms before redistribution (academic use stated). | **candidate_high** |
| [African Human Microbiome Portal (H3ABioNet)](https://microbiome.h3abionet.org/) | African human microbiome samples, metadata only | 14,889 records, 70 BioProjects, 72 articles | Harmonised, ontology-coded metadata (demographics, body site, disease) for African cohorts; filtered downloads. | BioProject / BioSample accession. | Open access (check reuse terms). | **candidate_medium** |
| [BugSigDB](https://bugsigdb.org/) | curated microbial signatures from published studies, all body sites | thousands of signatures from > 1,000 studies | Study-level curation: condition, body site, sequencing type, cohort location, linked PMID/DOI (CC-BY). | PMID / DOI → registry_study_papers → study. | CC-BY 4.0 | **candidate_medium** |
| [HMP / iHMP data portal](https://portal.hmpdacc.org/) | HMP1 and iHMP cohorts (multi-site, longitudinal) | > 30,000 files across the HMP programmes | Rich subject and visit metadata for the HMP cohorts (partly controlled access). | SRS / SRR accessions and BioProjects of the HMP studies. | Open for the public tier; controlled tier via dbGaP. | **candidate_medium** |
| [HumanMetagenomeDB](https://webapp.ufz.de/hmgdb/) | human metagenomes from SRA and MG-RAST, all body sites | 69,822 metagenomes, 203 standardised attributes (v1.0) | Standardised host attributes (body site, age, sex, disease, country) from archive metadata, ontology terms. | SRA sample / run accession. | Check (UFZ). | **candidate_medium** |
| [mBodyMap](https://mbodymap.microbiome.cloud/) | human microbes across body sites with health/disease associations; per-run curated phenotypes | tens of thousands of runs across 20+ body sites (see site) | Per-run body site, phenotype and disease annotation; taxon–disease associations. | run accession, project id. | Check. | **candidate_medium** |
| [Meta2DB (LLNL)](https://gdo-meta2db.llnl.gov/) | curated shotgun metagenomic feature sets with labelled health-state metadata | see Zenodo record 17315984 | Labelled sample metadata (health state) for shotgun studies; Centrifuge-based profiles. | SRA run accession. | Zenodo record (check). | **candidate_medium** |
| [MGnify (EBI Metagenomics)](https://www.ebi.ac.uk/metagenomics/) | analysed public metagenomes and amplicon studies, all biomes | hundreds of thousands of analysed samples | Biome (GOLD) classification, ENA-linked sample metadata via the API, uniform analyses. | ENA study / sample accession (native). | EMBL-EBI terms (open). | **candidate_medium** |
| [MicrobeAtlas](https://microbeatlas.org/) | all microbiome samples in SRA (amplicon and metagenomic), all biomes | 2,390,937 samples, 52,950 studies | Harmonised SSU-rRNA community profiles, extracted metadata keywords, environmental ontology and geographic coordinates per sample. | SRA sample / run accession. | Check. | **candidate_medium** |
| [MicrobiomeDB (VEuPathDB)](https://microbiomedb.org/) | curated microbiome studies (mostly 16S, some shotgun), human and other hosts | dozens of studies with rich sample metadata | Deeply curated per-sample metadata with ontology terms, downloadable per study. | SRA accessions where deposited. | Check (VEuPathDB data-use policy). | **candidate_medium** |
| [EMBERS (LLM extraction of metadata from 26,435 gut-microbiome papers)](https://www.biorxiv.org/content/10.1101/2024.10.26.620145) | paper-derived sample metadata for human gut studies | 26,435 papers | Automated extraction and harmonisation of sample metadata from papers — the same idea as our R3/R4 routes. | PMID → study; sample-level join depends on the released tables. | Check (preprint; data release status unknown). | **candidate_low** |
| [Human Microbiome Compendium (MicroBioMap)](https://microbiomap.org/) | human gut 16S amplicon samples from SRA | ≈ 168,000 samples | Uniformly processed 16S profiles and a harmonised sample_metadata.tsv (CC-BY). | SRA run / sample accession. | CC-BY | **candidate_low** |
| [PRIME](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12807763/) | human 16S amplicon studies with harmonised phenotypes | 53,449 samples, 111 studies, 93 body sites | Harmonised disease, demographics, body-site and protocol metadata for amplicon studies. | SRA accessions. | Check. | **candidate_low** |
| [gutMEGA, gutMDisorder, Disbiome, HMDAD, GutMetaNet, HGMT](https://gutmega.omicsbio.info/) | derived quantitative or literature-curated gut microbiome resources | — | Taxon–condition associations and processed abundances rather than per-sample archive-linked metadata. | PMID where given. | various | **not_applicable** |

## Per-resource assessment

### curatedMetagenomicData 3 (cMD 3) — candidate_high
Pasolli et al. 2017 Nat Methods; cMD 3 — Nature Communications 2025. Best per-sample external source for the core fields; already our gold standard for the infant fields. Ingest as an external curated table (route R2, evidence_source external.cmd3, evidence_locator = cMD study_name/sample_id, confidence 0.8) with precedence after the study's own supplementary tables. Disease codes map to health_conditions.yaml by rule.

### GMrepo v3 — candidate_high
Wu et al. 2020, Dai et al. 2022, Liu et al. 2026 NAR (v3). The 31,917 WGS runs overlap the catalog directly; disease → MeSH gives a mapping target for health_conditions.yaml. Ingest phenotype/age/sex/BMI as external.gmrepo_v3 rows (route R2, confidence 0.75) once redistribution terms are confirmed; otherwise use only as a cross-check and link out per study.

### African Human Microbiome Portal (H3ABioNet) — candidate_medium
Database 2024. Improves population coverage where archive attributes are thin; join on BioProject then BioSample.

### BugSigDB — candidate_medium
Geistlinger et al. 2023 Nat Biotechnol. Study-level condition and cohort-location annotations can support R4-like cohort statements (confidence ≤ 0.5) for studies whose papers BugSigDB curated.

### HMP / iHMP data portal — candidate_medium
Human Microbiome Project Consortium 2012; iHMP 2019. Per-visit metadata for the HMP gut samples in the catalog (thousands of samples); only the public tier can be redistributed.

### HumanMetagenomeDB — candidate_medium
Kasmanas et al. 2021 NAR. Derived from the same archive attributes as our R1, so mostly a consistency check for the 2020 snapshot; its ontology mappings (body site, disease) can validate our vocabularies.

### mBodyMap — candidate_medium
Jin et al. 2022 NAR. Body-site and disease annotations for non-gut sites make it a candidate when the oral, skin and vaginal scopes are curated.

### Meta2DB (LLNL) — candidate_medium
Meta2DB 2024 bioRxiv / 2026. Health-state labels for shotgun samples map to health_conditions.yaml; profiles out of scope.

### MGnify (EBI Metagenomics) — candidate_medium
Richardson et al. 2023 NAR. Biome assignments cross-check the registry's body-site classification for the studies MGnify analysed.

### MicrobeAtlas — candidate_medium
Cell 2026. Geography and environment annotations could fill country for samples without a geo attribute (as an inferred route with low confidence) and cross-check body-site classes; the profiles are rRNA-based and outside our scope.

### MicrobiomeDB (VEuPathDB) — candidate_medium
Oliveira et al. 2018 NAR. Small overlap but very high metadata quality for the studies it covers; worth an accession-level join test.

### EMBERS (LLM extraction of metadata from 26,435 gut-microbiome papers) — candidate_low
bioRxiv 2024. Methodologically closest to our approach; ingest only if a table with accessions and verbatim evidence is released.

### Human Microbiome Compendium (MicroBioMap) — candidate_low
Abdill et al. 2023 bioRxiv. Amplicon-only, so outside the shotgun scope; its harmonised metadata columns and the study list are a useful comparison for the registry's amplicon_misfiled calls.

### PRIME — candidate_low
2025. Amplicon-only; useful as a vocabulary reference for phenotype categories.

### gutMEGA, gutMDisorder, Disbiome, HMDAD, GutMetaNet, HGMT — not_applicable
various (2020–2025). No per-sample metadata to ingest; listed for completeness. HGMT (tumour cohorts, 18,630 stool samples) could supply cohort-level condition labels for immunotherapy studies.

## Proposed ingestion route

External curated per-sample metadata (cMD 3, GMrepo v3, HMP public tier, African Human Microbiome Portal, MicrobiomeDB, Meta2DB) would enter `gut_sample_determinations` as its own evidence rows: route `R2` (a per-sample table joined on archive accessions), `evidence_source = external.<resource>` (e.g. `external.cmd3`), `evidence_locator` = the resource's sample/study identifier, `evidence_quote` = the resource's raw value, `determined_by = external_ingest_v1:<resource>@<version>`, confidence 0.75–0.8, precedence after the study's own supplementary tables and before R3/R4 cohort statements. Disease vocabularies (cMD `study_condition`/`disease`, GMrepo MeSH terms) map to `config/vocab/health_conditions.yaml` by rule tables committed to the repository. Only resources whose terms permit redistribution are ingested; the others are linked per study (`gut_studies` gains `external_links`).

Study-level resources (BugSigDB, MGnify biome, mBodyMap, HGMT) would feed R4-style cohort statements (confidence ≤ 0.5) or cross-checks of the registry classification, never sample-level values.

## Order of work (proposal)

1. cMD 3 join test: `NCBI_accession` → registry runs → BioSample; count catalog samples covered per field; agreement with our R1/R2 values (a free precision check for the non-infant fields).
2. GMrepo v3: confirm redistribution terms; API pull of the 31,917 WGS runs; same join and agreement test.
3. HMP public tier and the African Human Microbiome Portal for cohorts with thin archive attributes.
4. Study-level cross-checks: BugSigDB conditions, MGnify biomes, mBodyMap body sites vs registry classification.

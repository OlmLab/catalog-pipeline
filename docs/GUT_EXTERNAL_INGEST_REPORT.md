# External curated resources ingested as R2 evidence — R2026.11 / package 1.11.0 (2026-09-28)

Owner decision: ingest the related curated-metadata resources rather than only list them. Ten leaf workers (one per resource) fetched each resource's bulk data or API, joined records to the catalog through archive accessions (run → BioSample, SRS/ERS → secondary sample, BioSample, or BioProject → study), mapped condition strings to `config/vocab/health_conditions.yaml` (written rules first, utility model for the long tail; mapping tables `data/inputs/gut/external/gut_ext_<id>_condition_map.parquet`), and emitted determination rows: route `R2`, `evidence_source = external.<id>`, `evidence_locator` = URL to the source record, `evidence_quote` = the source's raw value, `determined_by = external_ingest_v1:<id>@<version>`, confidence 0.6–0.75 (own archive attributes and own supplementary tables win ties by rank / confidence), `release_added R2026.11`.

| resource_id | rows | samples | studies | fields | notes |
|---|---|---|---|---|---|
| cmd (curatedMetagenomicDataCuration, commit 8059a76) | 141,320 | 24,547 | 118 | country, health_condition(+detail), sex, antibiotic_exposure, age, bmi | harmonised per-study `_sample.tsv` tables (superset of cMD 3 sampleMetadata); Artistic-2.0 |
| gmrepo (GMrepo v3 live API) | 140,605 | 39,805 | 286 | health_condition(+detail), country, sex, age, bmi, antibiotics | v3 endpoints discovered from the site bundle; MeSH → vocabulary (118 terms); no licence published |
| meta2db (Zenodo 17315984, CC-BY-4.0) | 51,784 | 11,338 | 78 | health_condition, country, sex, age, antibiotics, bmi, detail | 1,258 IBDMDB records without INSDC accessions skipped |
| hmgdb (HumanMetagenomeDB 1.1) | 34,330 | 19,876 | 165 | country, sex, age, health_condition(+detail), bmi, antibiotics | table read from the app's server-side endpoint; no licence published |
| microbiomedb (MicrobiomeDB build 37) | 18,921 | 5,113 | 10 | age, sex, country, antibiotics, health_condition(+detail), bmi | DiabImmune-1 unjoinable (internal ids) |
| microbeatlas (2026-01-29 bulk metadata) | 15,074 | 15,074 | 151 | country | reverse-geocoded coordinates, confidence 0.65; 38,014 rows of 17 systematically disagreeing studies dropped at assembly; no licence published |
| hmp_ihmp (IBDMDB hmp2_metadata 2018-08-20 + archived HMASM-690) | 14,152 | 2,456 | 3 | health_condition(+detail), sex, antibiotics, country, age | portal.hmpdacc.org API retired; www.hmpdacc.org compromised (not used) |
| mbodymap (files 2021-09-26) | 6,404 | 3,070 | 5 | health_condition, sex, detail | 139 infant samples coded with legacy `nec`; no licence published |
| ahmp (AHMP whole_data 2024-05-30) | 6,209 | 2,192 | 15 | country, health_condition(+detail), age | research-purposes disclaimer |
| bugsigdb (full dump 2026-09-28, CC-BY-4.0) | 103 (study_all) | — | 62 | country, antibiotic_exposure = no (exclusion criteria), health_condition | study-level statements only; 47 re-analysis links dropped |

Total 428,902 rows before precedence; after assembly the catalog holds 1,861,883 current determinations (R2 142,737 → 312,314). Coverage over all 579,252 samples: age 23.6 → 26.0 %, sex 28.6 → 31.0 %, BMI 5.3 → 7.0 %, country 90.1 → 91.1 %, health condition 31.0 → 37.5 %, antibiotics 12.5 → 16.5 %.

Agreement with pre-existing catalog values where both exist (leaf reports): sex 97.4–100 %, country 91–100 %, age within 10 % 94.7–99.9 %, BMI 100 %, health condition 52–87 % (differences mostly granularity — study-level `ibd_unspecified` vs per-sample `crohns_disease`/`ulcerative_colitis`, `other_cancer` vs a specific condition — and 102 PRJNA50637 samples where mBodyMap says pouchitis and the catalog other_cancer: flagged for review).

Not ingested: MGnify (biome only), Human Microbiome Compendium and PRIME (amplicon), EMBERS (no released tables), the derived resources (gutMEGA, gutMDisorder, Disbiome, HMDAD, GutMetaNet, HGMT). Terms caveat: GMrepo, HumanMetagenomeDB, MicrobeAtlas, mBodyMap and AHMP publish no licence; their values are redistributed with attribution and a link to the source record per row — the Sources page invites those projects to contact us.

Leaf reports: `data/inputs/gut/external/GUT_EXT_<id>_REPORT.md` (also saved as artifacts); per-study link tables `gut_ext_<id>_study_links.parquet`; summaries `gut_ext_<id>_summary.json`.

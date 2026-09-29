# Collections — curated, named sets of catalog studies and samples

`config/collections.yaml` defines the **Collections** section of the site: named sets of curated-catalog studies
and/or samples with pre-entered explorer filters (benchmark and reference cohorts, landmark population cohorts,
disease reference sets, age bands, lifestyle and design sets). The site generator (`site_generator/gen/build_site.py`,
Collections track) renders one card per entry and links each to the Samples explorer with the filters applied.
First shipped in R2026.12 / package 1.12.0.

## Schema (one entry per collection)

```yaml
collections:
  - id: crc-meta-analysis-cohorts          # slug: [a-z0-9]+(-[a-z0-9]+)*, unique
    title: Colorectal cancer meta-analysis cohorts (Wirbel / Thomas 2019)
    kind: disease                          # benchmark | population | disease | design | age | lifestyle | other
    blurb: <= 60 words, factual — what the set is and why someone would want it
    studies: [PRJEB6070, PRJEB7774, ...]   # optional; every accession MUST be in gut_studies.parquet
    filters:                               # optional; keys among age_category, country, health_condition, lifestyle,
      health_condition: [colorectal_cancer]  #   antibiotic_exposure, sex, collection_year, study_accession,
      body_site_class: [primary]             #   body_site_class, min_samples_per_subject
      min_samples_per_subject: {min: 5}      # list = any-of; {min, max} = inclusive range
    references:
      - {label: Wirbel et al. 2019, Nature Medicine, url: https://doi.org/10.1038/s41591-019-0406-6}
    notes: free text shown under the card (caveats, what was left out and why)
```

Semantics: `studies` restricts to the listed accessions; `filters` restrict samples; when both are present the
filters apply **within** the listed studies. A collection needs at least one of the two. Filter values must come from
the catalog vocabularies: `age_category` from `config/packs/gut.yaml` (`neonate`, `infant`, `child`, `adolescent`,
`adult`, `elderly`, `unknown`), `health_condition` from `config/vocab/health_conditions.yaml`, `lifestyle` from
`config/vocab/lifestyle.yaml`, `country` as ISO-3166 alpha-2, `sex` in `female | male | unknown`,
`antibiotic_exposure` in `yes | no | unknown`, `body_site_class` in `primary | linked | unknown | excluded`.
`lifestyle` and `collection_year` are populated from package 1.12.0 onward; a lifestyle-based collection must therefore
**also** list its studies explicitly so it renders on releases where the column is still empty.

## How to propose a collection

1. Fork `OlmLab/catalog-pipeline` and edit `config/collections.yaml` (append an entry; keep ids stable once shipped —
   rename by adding a new entry and retiring the old one in `notes`).
2. Verify every accession exists in the current package: `duckdb -c "select study_accession, study_title, n_samples
   from 'gut_studies.parquet' where study_accession in ('PRJ...')"` — accessions that are not catalog studies are
   dropped at build time and reported, never silently kept. If the study is a human gut shotgun study missing from the
   catalog, open a registry issue instead (it must enter through triage; see RUNBOOK §2).
3. Run `python scripts/build_collections.py --check` (validates schema, vocabularies, accession existence, blurb
   length, and that every filter-only collection returns >= 100 samples) and attach the printed preview
   (`n_studies`, `n_samples`) to the PR description.
4. Cite how you identified the accessions (paper data-availability statement, ENA record, BioProject search) in
   `references`; blurbs state facts that can be checked against the paper or the ENA record — no claims about
   sample quality or results.
5. Open a PR titled `collections: add <id>`. The owner reviews for scope (human gut shotgun only), non-duplication and
   naming; merged collections ship with the next release and appear in `collections_preview.csv` of the package.

## Provenance rules

Collections are curation, so the catalog's evidence rules apply: a study belongs to a collection only if its paper,
ENA record or study description states the property the collection is about (e.g. the word "Hadza", an FMT trial
registration, a mock-community control). Filter-based membership is computed from per-sample determinations that
each carry their own evidence quote; the collection inherits that provenance. Nothing is inferred from country or
centre name alone.

# Community contributions — the `contribute/` worklist and the Issue intake (R2026.2, package 1.4.0)

Narrative for `config/contribute.yaml` (the frozen schema), `src/catalog/contribute/build_worklist.py` (the tables) and the
site's `contribute/` pages. MATURITY_PLAN §3.2 (worklist), §3.3 "alternative with zero custom backend" and §3.4 step 1 (intake).

## 1. What the worklist is

Two read-only tables shipped in every package from 1.4.0:

| file | rows | one row per |
|---|---|---|
| `contribute_worklist.csv` | one per **open** study | included or uncertain study for which at least one of the six worklist fields is below the coverage threshold |
| `contribute_worklist_fields.csv` | 6 per open study | study × field (age, delivery, feeding, preterm, antibiotics, probiotic) |

"Open" = `universe_studies_all.triage_verdict ∈ {include, uncertain}` and NOT complete. A study is **complete** when every one
of the six fields has coverage ≥ `missing_threshold` (0.5) on its **catalog_scope** samples; a study with zero catalog_scope
samples is judged on body-site scope (`body_site_class ∈ {primary, unknown}`) instead. Complete studies are not listed
(their field-level code would be `complete`). Coverage is recomputed from `sample_metadata_wide` at build time — the
shipped `study_field_coverage_matrix.csv` is on a different scope and is not used.

Ranking: `priority_score = Σ_{missing f} weight_f × (1 − coverage_f) × log10(n_catalog_scope + 1)` with weights
age 3 · delivery 2 · feeding 2 · preterm 1.5 · antibiotics 1 · probiotic 0.5 (the extraction-worklist v3 weights); ties by
`n_samples` desc, then accession. Studies with no catalog_scope samples therefore score 0 and sit at the end (they are still
listed: their coverage columns are on body-site scope).

## 2. Blocker codes — how each is derived

One code per study = the dominant reason it is open. Uncertain studies always get `archive_only_uncertain` (detail =
`human_review_queue.review_round: note`). For included studies the rules fire in this order (first match wins):

| order | blocker_code | fires when | input column |
|---|---|---|---|
| 1 | `controlled_access` | the study accession or its `cohort_id` is in `controlled_access_registry.csv` with a non-open tier, or `extraction_worklist.controlled_access` / `universe_studies_all.controlled_access` is true | registry `accession`, `accession_type = cohort`; the registry's `paper_ids` are deliberately **not** used (a paper citing an EGA dataset may also reuse many open BioProjects) |
| 2 | `no_linked_paper` | 0 rows for the study in `study_paper_links.csv` | `study_paper_links.study_accession` |
| 3 | `paywalled_abstract_only` | linked paper(s) but `extraction_worklist.access_tier` starts with `C_`/`D_`/`E_` | `extraction_worklist_v3.access_tier` |
| 4 | `tables_unjoinable_need_key` | study is one of the 77 `r2_rescue_studies.csv` (the RESCUE_REPORT_v2 per-study table) | `RESCUE_REPORT_v2.md` "sid_col forms" → `blocker_detail` id form and `unlock_text` |
| 5 | `pdf_only_supplement` | the study's linked papers have supplementary members in `supp_inventory.parquet` but none with `member_type == table` | `supp_inventory.member_type` joined through `study_paper_links.paper_id` |
| 6 | `no_supplement_found` | linked paper(s) but 0 inventoried supplementary members | same join, 0 rows |
| 7 | `unitless_age_needs_curator` | a `recoverability.note` or the RESCUE_REPORT status mentions a unit-less age column | `recoverability.parquet.note`; RESCUE_REPORT status `unitless_age_header_unit_from_model` |
| 8 | `partial_coverage` | everything else (paper + tables exist, some fields still below threshold) | recomputed coverage |

`blocker_detail` (≤ 200 chars) quotes the deciding evidence (counts, access tier, id forms, review note). `unlock_text`
(≤ 200 chars, imperative) is the `unlock_templates[blocker_code]` string from `contribute.yaml` with `{id_form}`,
`{missing_fields}`, `{accession}` substituted — nothing is free-written. `contribution_type` (the primary ask) is
`blocker_to_contribution_type[blocker_code]`.

Field-level codes (`contribute_worklist_fields.blocker_code`): `complete` when the field reaches the threshold, else the
study code; under `unitless_age_needs_curator` only the age field carries that code, the others `partial_coverage`.
`best_tier_*` is the best recoverability tier for the study × field in `recoverability.parquet` (R1 archive attribute ·
R2 supplementary table · R3 paper text · R4 abstract · R0 nothing found) and `evidence` (≤ 120 chars) its first evidence
quote and note.

## 3. Contribution types and the Issue form

| contribution_type | ask |
|---|---|
| `per_sample_table` | a per-sample CSV/TSV/XLSX for the study, one row per sample keyed by run/BioSample accession or library name, with the missing columns |
| `id_key` | a key file mapping the paper's sample names to BioSample/run accessions |
| `paper_pointer` | PMID/DOI of the paper describing the study's own data |
| `age_schedule` | the unit of the age column or the sampling schedule, with the paper section |
| `verdict_evidence` | evidence that settles the triage verdict (infant shotgun metagenome yes/no) |

`issue_url` opens a **prefilled GitHub Issue** in `OlmLab/infant-gut-catalog` using the form
`.github/ISSUE_TEMPLATE/catalog-contribution.yml` (name "Catalog contribution", label `contribution`); GitHub prefills the
form inputs/dropdowns whose ids match the query keys `study_accession`, `contribution_type`, `release_tag` and the `title`.
Form fields: `study_accession` (required), `contribution_type` (dropdown, required), `source` (dropdown:
journal_supplement_url · author_correspondence · own_lab_records · other, required), `source_url`, `licence` (checkbox:
"I confirm the uploaded table may be redistributed under CC-BY-4.0, or I ask that only derived values be published",
required), `note` (textarea — the contributor drags the CSV/TSV/XLSX into it; GitHub stores it under
`github.com/user-attachments/…`), `release_tag` (prefilled). Uploads must contain **no e-mail addresses and no names of
study participants**.

## 4. How a contribution flows

1. **Issue** — the contributor clicks Contribute on the site (worklist row or the "Help complete this study" panel), fills the
   prefilled form, attaches the table. Nothing executes; the Issue is the public, auditable queue.
2. **Ingest (deterministic, `ingest_contributions.py`, RUNBOOK stage 4b)** — lists Issues labelled `contribution`, downloads the
   attachment, applies the size/type gate (readable table, ≤ N columns, no executable content) and the **same R2 joinability
   gate** as the supplement pipeline (`r2_supp_extract_v2` / `r2_rescue_map`): does an ID column map to the study's own
   BioSamples/runs/library names/aliases, directly or through an uploaded key? Verdict per Issue:
   `accepted_for_review | unjoinable | duplicate_of_existing | rejected`, posted back as a comment together with what is
   missing ("ids look like T1_S23; a key to SRR accessions is needed").
3. **Curator (Claude session, weekly)** — accepted uploads run the normal extraction contract (validate_row on every value,
   route R2, `evidence_source = contributor_table:<issue_number>`, confidence per the R2 rules; conflicts with existing R1/R2
   values go to the conflict queue, never overwrite). Contributed tables never override an archive attribute (R1).
4. **Release attribution** — applied values enter the next release with `release_added = R<YYYY>.<n>`; the study page shows
   "Per-sample table contributed via Issue #<n>, <date>" (opt-in display name; e-mail never shown). The study leaves the
   worklist when it becomes complete, and its worklist row gets `release_retired` = that release.

## 5. Provenance of every column

| column(s) | source |
|---|---|
| `study_title`, `cohort_id`, `cohort_name`, `triage_verdict`, `n_samples`, `n_infant_samples_est` | `universe_studies_all.parquet` |
| `n_catalog_scope`, `coverage_*`, `n_with_value` | recomputed from `sample_metadata_wide.parquet` (`catalog_scope`, `body_site_class`, the six field columns) |
| `best_tier_*`, field `evidence` | `recoverability.parquet` (best tier per study × field) |
| `blocker_code`, `blocker_detail`, `unlock_text`, `contribution_type` | §2 rules; `config/contribute.yaml` templates |
| `n_linked_papers`, `own_data_pmids` | `study_paper_links.csv` |
| `n_supp_tables_inventoried` | `supp_inventory.parquet` (`member_type == table`) via `study_paper_links.paper_id` |
| `controlled_access` | §2 rule 1 |
| `priority_score` | formula in §1 (the test recomputes it from the row) |
| `ena_url`, `ncbi_url` | `study_metadata_wide` (fallback: `archive_urls` templates) |
| `issue_url` | `issue.url_template` |
| `release_added`, `release_retired`, `package_added` | bitemporal columns (docs/RELEASES.md) |

The artifact inputs are registered in `config/inputs.json` group `contribute` (artifact id, version id, sha256);
`bootstrap.py` materialises them under `data/inputs/contribute/`. Rebuild: `make worklist` (inside `make release`).

## 6. "Flag an issue" — the simple finding form (R2026.12)

Every study and cohort page carries one **Flag an issue** link (the former "Confirm correct" button was removed). It opens the
two-question GitHub Issue form `site_generator/gen/issue_templates/simple-finding.yml` in the Issues repo
(`config/site.yaml github.issues.repo`, template `github.issues.template = simple-finding.yml`, label `finding`):

| field id | asked as | prefilled by the link |
|---|---|---|
| `problem` | dropdown: a value is wrong · a value is missing · the study should not be in the catalog · something else | — |
| `details` | one free-text box (which field / sample, the correct value, where it can be checked) | — |
| `accession` | "filled automatically — leave as is" | study accession or cohort id |
| `release_id` | "filled automatically — leave as is" | `VERSION.json release_id` |
| `page_url` | "filled automatically — leave as is" | canonical URL of the page |

GitHub issue forms have no hidden or read-only fields, so the three prefilled values are ordinary inputs labelled as filled
automatically. The detailed audit form `catalog-finding.yml` stays installed for the Auditor tooling (`ingest_issues.py` reads
both labels `finding`); a simple finding is triaged by a curator into a full finding row (evidence quote ≤ 12 words, route,
confidence) before it is applied — nothing enters the tables without evidence. **Install:** copy the file into
`<site clone>/.github/ISSUE_TEMPLATE/simple-finding.yml` (the `make install-workflows` target copies the two existing templates;
add this one to its copy list or copy it by hand) and commit on the site repo's `main` (owner).


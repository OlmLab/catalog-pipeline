# EXPANSION.md — from the infant gut catalog to a registry of all human shotgun metagenomes

*S0 track ("Scope and vocabularies"), 2026-09-27. Companion to `docs/SCALE_UP_PLAN.md` (sizing, phasing, budgets); this
file is the working specification the code reads. Machine-readable copies: `config/scope.yaml`, `config/vocab/*.yaml`,
`audit/registry_schema.json`.*

## 1. What changes conceptually (SCALE_UP_PLAN §2)

| before (infant catalog) | after (registry + curated scopes) |
|---|---|
| one question per study — *infant gut shotgun, yes/no* | **classification**: human? · which body site(s)? · which life stage(s)? · which population(s)? · assay · access |
| `exclude` is the common outcome (9,140 of 9,581 screened studies) | exclusion is reserved for **non-human, non-metagenome and non-shotgun** deposits; every human shotgun study stays in the registry |
| one product (package + site) | **two tiers**: a registry tier for every human shotgun study/run (archive-only metadata, route R1, Sandpiper, papers, authors) and curated tiers per scope (R2–R4 extraction, field packs) |
| infant field vocabulary (16 fields) | a **core field pack** for every scope plus **scope packs** (infant, gut, oral, vaginal_urogenital, skin, respiratory) declared in `config/scope.yaml`, not in code |
| taxon-framed enumeration | frame-free sweep + BioSample-attribute sweep over `library_source=METAGENOMIC` WGS/WXS (+ misfiled GENOMIC under human taxa); the human-signal rule is the pre-filter |

The infant gut catalog becomes the **first curated scope** (`infant_gut`, `curated: true`). Its verdicts are not recomputed:
they enter the registry as `in_infant_catalog` / `infant_reason_code` and as deterministic priors for the classifier (§5).

## 2. Registry tier vs curated tier

| | registry tier | curated tier (per scope) |
|---|---|---|
| unit | ENA study (`registry_studies`) and run (`registry_runs`) | BioSample (or run for pooled deposits) — `sample_metadata_wide` |
| metadata | archive fields only (route R1) + study-level classification with evidence | R1–R4 per-sample extraction, subject/timepoint resolution, audits |
| classification | deterministic rules + Sonnet ×2 / Opus adjudication (§5) | scope triage (the current infant rubric generalised by the scope's prompt fragment) |
| cost | ≈ 4–7 k tokens / LLM-judged study; most studies never reach the LLM | 25–50 k tokens / included study |
| tables | `registry_studies.parquet`, `registry_runs.parquet` (working_data), `registry_universe_audit.csv` | the existing package tables, one package per scope |
| site | `registry/` section: all studies, body-site / life-stage facets, authors, links into scope pages | the scope site (the current infant site is the first) |

## 3. Deviation from SCALE_UP_PLAN §3 (owner-authorised 2026-09-27)

The plan proposed separate repositories (`human-metagenome-registry-data`, a registry index site, one Pages repo per scope).
**Decision: the registry tier lives inside the existing repos.** `registry_*` tables are added to the data package built by
`catalog-pipeline` and published in `infant-gut-catalog-data`; the site gains a `registry/` section; the infant catalog is one
scope inside it. Consequences that this track honours:

* registry tables follow the package conventions — bitemporal columns `release_added / release_retired / package_added`
  appended last (`config/releases.yaml → registry_tables`, `built_with_release_columns: true`), deterministic builds
  (same inputs → byte-identical parquet), F7 (no session identifiers or e-mail addresses in any published text);
* `registry_runs.parquet` (≈ 1.5 M rows) is too large for the package zip and for Pages: it is ONE working_data artifact,
  columns restricted to the 43 lean ENA pull fields + `found_by` (`resweep_universe.LEAN_FIELDS`), joined on demand;
* the explorer of the registry section works on `registry_studies` and run-level summaries, never on per-sample fields
  (R1-12); the separate-repo layout stays available later by moving the tables — nothing here depends on the location.

## 4. How a scope is added (config only)

1. Append an entry to `config/scope.yaml → scopes` (`id`, `label`, `definition`, `tier`, `body_sites`, `life_stages`,
   `curated`, `field_pack`; optional `membership_rule` when the rule is not the default body-site ∧ life-stage test).
2. If new vocabulary codes are needed, append them to the relevant `config/vocab/*.yaml` (codes are never renamed or
   removed; `schema_version` stays 1 while columns are only appended).
3. If the scope is curated, add `config/packs/<field_pack>.yaml` (fields + prompt fragments) — the extraction routes read it.
4. Run `make registry-build` (scope memberships are re-derived for every study) and `make test`
   (`tests/test_registry.py::test_vocabularies_match_frozen_spec` pins the frozen lists — extend the expected list in the
   same commit, which is the reviewable record of the change).

`build_registry.derive_scope_memberships` is the only code that knows scope ids, and it reads them from the YAML.

## 5. Classification cascade

```
registry universe study (frozen columns; aggregated run/sample fields)
  │
  ├─ deterministic_prior   infant universe verdicts (universe_studies_all): host_nonhuman/environmental/synthetic → host_human=no;
  │                        age_adult_only → adult; age_child_over_36m → child; age_maternal_only → adult + pregnant;
  │                        site_excluded/site_unknown → body site from body_site_call; include → infant + gut_stool
  ├─ deterministic_rule    host_tax_id 9606 / non-9606; human vs animal-environment text; synthetic markers;
  │                        assay from library fields (config/vocab/assay.yaml rules); body sites and life stages from the
  │                        term matchers over title, sample titles, isolation_source, host_body_site, environmental_medium,
  │                        dev_stage (+ numeric ages WITH a unit; taxon name only as a 0.5 prior — taxon is not body site)
  │                        → evidence rows {source, quote ≤ 12 words} validated by validate_evidence; needs_llm when host is
  │                        mixed/unknown, site unknown / weak / tie, life stage unknown for a human study, assay adjudication,
  │                        conflicting human+animal signals, or confidence < 0.8
  ├─ sonnet_x2             batches of ≤ 6 studies, two independent Sonnet replicates (role `rubric`), strict JSON tool output,
  │                        every id returned or a sentinel row, validator per decision (vocabulary + evidence + source label);
  │                        agreement on (host, assay, primary site, primary life stage) → stage sonnet_x2, confidence = mean
  ├─ opus_adjudicated      disagreement or a missing replicate → Opus (role `adjudicate`) sees both replicate answers and
  │                        the deterministic hint; its validated answer is final for this release
  └─ pending               still unresolved (sentinel, validator_rejected) → human review queue on the site
```
Models are resolved through `catalog.models` roles (`config/models.yaml`); no literal model ids exist in the repository.
`host.llm` is used only when the root session passes `host` (leaf-worker convention, sub-agents cannot delegate).

**Evidence contract** (curation skill Rules 1–3, 6, 12–14, applied to every registry value): a labelled source
(`study.title`, `study.description`, `sample.title`, `sample.attr.<key>`, `run.<field>`, `external_curation.infant_catalog`),
a quote of ≤ 12 words copied from that field, sentinels (`unknown`, `unknown_site`, `unknown_age`) instead of guesses,
controlled codes only. Traps carried into the prompt and the matchers: *Infantis*, taxon ≠ body site, animal infant naming,
`OTHER` hides shotgun, culture-enriched deposits, blank taxon, word boundaries (rat/kid/cat/Gutierrez/colonization),
rodent-scale ages, "children" cohorts that may include 0–3 y, meconium ≠ shotgun.

## 6. Tables (audit/registry_schema.json, schema_version 1)

* `registry_studies.parquet` — one row per study; 42 columns incl. the frozen enumeration columns, the classification
  columns with JSON evidence, `in_infant_catalog`, `scope_memberships`, bitemporal columns.
* `registry_runs.parquet` — one row per run; 43 lean ENA fields + `found_by` + bitemporal (working_data artifact).
* `registry_universe_audit.csv` — per enumeration slice: ENA count vs rows pulled, completeness.
* `REGISTRY_REPORT.md` — counts by host, body site, life stage, assay, stage, scope (fixture runs are labelled provisional).

## 7. Make targets and tests

`make registry-classify-det` (deterministic classification of the registry universe or, when the enumeration track's table is
absent, of the 200-study fixture) · `make registry-build` (assemble `registry_studies.parquet` + report; `REGISTRY_LLM=` adds
the LLM table) · `make registry-fixture` (rebuild the fixture from the 1.5.0 universe). `tests/test_registry.py` covers the
frozen vocabularies, matcher traps, 30 synthetic and 200 real universe rows (non-human → `host_human=no`; includes →
`infant` + `gut_stool` + `infant_gut`), the LLM parser/validator/agreement on synthetic responses, schema conformance,
determinism and scope derivation.

## 8. Open items for the following tracks

* Enumeration track: `registry_universe_studies.parquet` must carry, beyond the frozen columns, the aggregated sample fields
  the classifier reads (`sample_titles_sample`, `isolation_sources`, `environmental_medium`, `host_body_sites`, `ages`,
  `dev_stages`, `instrument_models`, `library_selections`, `library_layouts`, `base_count_median`, `read_count_median`,
  `serovars`, `sub_species`, `strains`) — `build_registry.normalise_universe` accepts the singular spellings too.
* LLM run: dispatch `classify_llm.run_llm_stage` from the root session per RUNBOOK leaf-worker conventions; budget per
  `config/budgets.yaml` (≈ 4.0–7.2 k tokens/study; the fixture flags 62 of 200 studies for the LLM stage).
* Site track: `registry/` section reading `registry_studies.parquet`; `config/site.yaml` facets from the vocabularies.
* `gut_stool` + `unknown_age` studies belong only to `human_all` until the LLM stage or R1 attributes resolve the life stage;
  the report's `unknown_age` count is the size of that queue.

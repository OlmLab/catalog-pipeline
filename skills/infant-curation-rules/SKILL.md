---
name: infant-curation-rules
description: "Evidence-first rules for every value an agent commits to the Infant Gut Shotgun-Metagenome Catalog: study triage verdicts, paper-study links, and per-sample metadata (age, delivery mode, feeding, preterm, antibiotics, probiotics). Load before judging any study, paper, or sample record in this project, and whenever a triage/extraction task says to read the curation rules. Defines the evidence anchor, the omit-rather-than-guess sentinel, the no-identifiers-from-memory rule, the controlled reason codes, the false-positive traps, and the validators in kernel.py."
---

# Infant catalog curation rules

Adapted from NMDC's `nmdc-curation-rules` (github microbiomedata/nmdc-ingest-agent) for the
Anthropic-grant infant microbiome project. These rules govern every value an agent commits on
behalf of a curator, whether the agent is a triage child judging a study record, a linking child
matching a paper to an accession, or an extraction child reading a supplementary table.

A **committed** value is any value written to an output row with an outcome other than
`sentinel_no_evidence`. Sentinels are not commits — they are the explicit no-evidence outcome and
a valid deliverable.

## Scope you are enforcing (locked 2026-09-14; source: `scope_constants.py`)

* DNA shotgun metagenomics only: `library_source=METAGENOMIC`, `library_strategy in {WGS, WXS}`;
  `OTHER`/`Targeted-Capture` are adjudication cases, never automatic includes.
  Amplicon (16S/18S/ITS), metatranscriptomics/RNA-seq, proteomics, metabolomics: out.
  Cultured isolate genomes (`library_source=GENOMIC`): out of primary scope, recorded separately.
* Human subjects aged 0–36 months (birth through third birthday). Preterm neonates included.
  A study with only 4-year-olds, or only adults, or only pregnant women, does not qualify.
* Gut/stool/faeces/meconium/intestinal is primary. Breast milk, maternal stool, vaginal samples
  count ONLY inside a study that also samples infants; tag them by `body_site`.
* Paywalled papers: curate from abstract + archive metadata with `evidence_limited_to=abstract`
  on every derived value and confidence capped at 0.6.

## Rules

1. **Evidence anchor.** Every commit carries one or more `evidence` rows of the shape
   `{"source": "<labeled source>", "quote": "<≤12 words, verbatim or close paraphrase>"}`.
   Sources are explicit labels — never bare quotes. Allowed source labels:
   `study.title`, `study.abstract`, `study.description`, `sample.title`, `sample.attr.<key>`
   (e.g. `sample.attr.host_age`), `run.library_strategy`, `run.instrument_model`,
   `paper.title`, `paper.abstract`, `paper.fulltext.<section>` (methods, results,
   data_availability), `paper.supp.<filename>[<sheet>!<column>]`, `paper.supp.table` (a
   summarised per-sample table: quote = column header + one matched value),
   `external_curation.<source>` (e.g. `external_curation.cmd` for curatedMetagenomicData
   sample metadata — a truth source, never a triage input), `sample_id_pattern`
   (for conventions like `_3M`, `M/B` pair codes), `sibling_consensus N=<n>`,
   `cohort_default` (a study-level statement propagated to samples — see Rule 9).

2. **No tautology.** Domain-general statements ("infants have immature microbiomes",
   "meconium is the first stool", "NEC occurs in preterm infants") do not justify a value
   without a per-record anchor. If the only justification is general knowledge, refuse.

3. **Omit rather than guess.** If Rules 1–2 cannot be satisfied, write
   `outcome: "sentinel_no_evidence"` and move on. An empty field with a sentinel is a correct
   result that surfaces work for the curator. Never fabricate evidence to fill a field.

4. **No identifiers from memory.** Every accession (PRJ*, SAM*, SRR/ERR/DRR, SRX/ERX, PMID,
   PMCID, DOI) and every ontology ID you commit must appear in a record you were shown in this
   task — an archive field, a cached paper, a supplementary file, or an API result. Do not
   complete, correct, or recall accessions. Models memorize public identifiers; a plausible
   accession you "remember" is a hallucination until it is read from a source.

5. **Reason codes are controlled.** Every exclusion carries exactly one `reason_code` from the
   vocabulary below. Do not invent codes. If none fits, use the nearest and add a `note`.
   `assay_amplicon` · `assay_amplicon_misfiled` · `assay_rna` · `assay_isolate_genome` ·
   `assay_other_nonshotgun` · `assay_assembly_only` · `host_nonhuman` · `host_environmental` ·
   `host_synthetic` · `age_adult_only` · `age_child_over_36m` · `age_maternal_only` ·
   `age_unknown_no_evidence` · `site_excluded` · `site_unknown` · `fp_salmonella_infantis` ·
   `fp_bifido_infantis` · `fp_name_only` · `access_controlled` · `access_suppressed` ·
   `dup_mirror` · `dup_reanalysis`

6. **Know the traps.** All of these were observed live in this archive:
   * **"Infantis" is a name collision.** *Salmonella enterica* serovar Infantis and
     *Bifidobacterium longum* subsp. *infantis* are bacteria. Check `serovar`, `sub_species`,
     `strain` fields before reading "infantis" as a human infant.
   * **Taxon is not body site.** A study filed under taxon "human gut metagenome" may be
     adenoid, oral, skin, sputum, or nasal (PRJEB72800 is the standing example). Trust
     `study.title`, `sample.title`, body-site, `environmental_medium`, `isolation_source`.
   * **Animal studies with infant-like naming**: piglet, mouse pup, infant macaque, calf,
     chick, neonatal rat. The grant's own example is PRJNA716514 (swine). Host taxon ID
     must be 9606.
   * **Adult cohorts with an incidental infant subgroup** qualify only if infant samples are
     identifiable; commit with `n_infant_samples_est` and cite the evidence.
   * **Amplicon deposited as WGS**: a `target_gene`, primer, or "V3-V4" value on a WGS run is
     `assay_amplicon_misfiled`.
   * **Simulated / mock / synthetic** communities: `host_synthetic`.
   * **Pooled meta-analysis tables are not per-study evidence.** A supplementary table that
     lists thousands of samples with age ≤3 y may pool 50–80 public studies (life-span atlases,
     reference catalogues). Rows count for a study ONLY if the sample-ID column maps to that
     study's own run/sample/experiment accessions or library names. Cite as `paper.supp.table`
     with the matched count; unmatched pooled rows are `age_unknown_no_evidence`.
   * **Incidental infant subgroups hide from every archive signal.** Adult/child cohorts with
     2–30 infant samples (Tett 2019, Pehrsson 2016, Dhakan 2019, Averina 2020) carry no infant
     term in title, description, sample titles or attributes; only a linked paper's per-sample
     table reveals them. Recall on these is bounded by supplement access, and the catalog
     reports study-level and sample-weighted recall separately for that reason.
   * **"OTHER" hides shotgun.** Whole deposits labelled `library_strategy=OTHER` with
     NovaSeq/NextSeq depth (median ≥0.4 Gb/run, 150–300 nt, no target_gene) are shotgun
     metagenomes misfiled by the submitter (11 of 436 catalog studies). Adjudicate, do not
     auto-exclude; cite `run.library_strategy` + `run.base_count`.
   * **Shallow MiSeq WGS looks like amplicon by depth alone.** ~5e7 bases/run, 2×300,
     `library_selection=RANDOM`, insert 450–550 is compatible with both; never assign
     `assay_amplicon_misfiled` on depth without a paper check.
   * **"children"/"preschool" cohorts may contain 0–36 m subjects.** cMD lists 9–28 infant
     samples inside cohorts described as children; `age_child_over_36m` requires a stated
     minimum age or a per-sample table, otherwise use `age_unknown_no_evidence` + unsure.
   * **Bacterial isolate deposits from infant cohorts** (`library_source=GENOMIC`) are out of
     primary scope even when cMD or a paper treats the cohort as metagenomic — record the
     disagreement in `note`, keep `assay_isolate_genome`.
   * **Word-boundary matching.** "rat" inside "ulcerative", "kid" inside "kidney", "cat"
     inside "applications" are not hosts. Use whole-word matches.

7. **Validate before commit.** Call the validators in `kernel.py` (loaded with this skill)
   before writing any row: `validate_evidence(rows)`, `validate_reason_code(code)`,
   `validate_age(value, unit)`, `validate_accession_seen(acc, sources_text)`. A failed
   validator means revert to sentinel with `outcome: "validator_rejected"` and record which
   check failed — never silently downgrade.

8. **One reason per commit, terse.** Quote ≤12 words. If you cannot say it in 12 words,
   the evidence is too thin or you are constructing a justification instead of reading one.

9. **Cohort defaults propagate explicitly.** A study-level statement ("all infants were
   vaginally delivered and exclusively breastfed") may be committed to each sample with
   `source: "cohort_default"`, `outcome: "predicted"`, and the study-level quote — never as
   if it were a per-sample observation.

10. **Numeric age is a triple.** Commit age as `{value, unit, source}` exactly as written
    (e.g. `{4, "months", "sample.attr.host_age"}`); conversion to `age_days` is done by
    `age_to_days()` deterministically, and the result must fall in 0–1,100 days for an
    in-scope infant sample. Corrected gestational age and postnatal age are different fields.

12. **Quotes are ≤12 words, hard.** Models routinely produce 15–25-word quotes when asked for
    "≤12 words"; ~8% of Sonnet rows were validator-rejected for this. Prompt for "the shortest
    decisive span, 3–8 words ideal" and batch-validate; keep rejected rows as
    `validator_rejected`, then re-judge only the rejected ids.
13. **Batched judgments must return every id.** At 25 items per request whole batches were
    silently dropped 3–9% of the time; every missing id gets a `sentinel_row` (slot
    `<task>_missing`) and is re-run at a smaller batch (10) with a higher `max_tokens`.
    Never impute a verdict for a missing id.
14. **Replicate, then adjudicate.** Sonnet ×3 on include/unsure candidates (unanimous 73%,
    majority 25%, split 2%); Opus adjudicates non-unanimous and uncertain studies and a blind
    200-study κ sample (observed κ 0.77 three-class / 0.85 include-vs-not). Opus leaves ~50% of
    adjudicated studies `uncertain` — that is the human queue, not a failure.
15. **Deterministic include by supplementary table.** A study whose linked per-sample table maps
    ≥1 of the study's own accessions to age ≤1,100 days, with WGS runs and no host/assay/site
    exclusion, is `included` by rule (`model: deterministic`, stage `supp_rescue_deterministic`,
    `n_infant_samples_est` = matched rows). Symmetric to deterministic exclusion.

11. **Abstract-only evidence is flagged.** When the paper's access tier is C/D/E, every value
    derived from it carries `evidence_limited_to: "abstract"` and `confidence ≤ 0.6`.

## Triage cascade (as run for release 2026-09-18)

deterministic auto-exclude (host taxon / isolate / amplicon-only; Sonnet audit of 100) →
Haiku batched screen (40 studies/request; slot `infant_screen`) → Sonnet 4-criterion rubric on
candidates (4/request) → Sonnet ×3 replicates on include/unsure → Opus adjudication →
literature channel (Haiku 4-slot abstract screen 25/request; accession mining of full-text JATS
+ supplements; deterministic + Sonnet linking) → Sonnet confirmation of paper-linked studies
WITH paper context → supplementary-table rescue (Rule 15) → gap-fill re-enumeration.
Measured costs: Haiku ~775 tok/paper, Sonnet ~1.15k tok/study, fixed ~4.9k tok/request.
Sub-agents cannot delegate: every LLM fan-out is dispatched from the root session as leaf
workers (`llm_batch_common.py`, `run_paper_screen.py`, `run_sonnet_confirm.py` artifacts).

Known enumeration traps (fixed 2026-09-18): ENA files "human feces metagenome" under taxid
2705415 (not 3007725); the OTHER/Targeted-Capture slice must be enumerated for `tax_eq(9606)`
as well as for the metagenome taxa; studies under the generic taxon 256318 "metagenome" with no
`host_tax_id` are reachable only through the literature.


### Traps added 2026-09-24 (growth round 2 + human-review round 2)
* **Blank / off-frame taxon deposits.** Many 2025–26 infant cohorts are deposited with NO tax_id or under a generic taxon; a taxon-framed enumeration never sees them. Judge from record content; never treat a blank taxon as evidence against human origin.
* **Animal hosts invisible in ENA portal rows.** Some SRA-mirrored deposits have no ENA BioSample; host species (red deer, chicken, sheep, sow, broiler) appears only in the NCBI BioSample (eutils). When host fields are empty and the title is bare, fetch the NCBI BioSample before committing.
* **Rodent age trap.** `age: 10 weeks` with host `missing`/blank on a "gut microbiome" deposit is far more often a mouse/rat than a human infant. Require a human host or human-specific text before reading a weeks-scale age as infant evidence.
* **Culture-enriched / plate-sweep metagenomes** (e.g. Chatinkha nursery Klebsiella study) are shotgun sequencing of enrichment cultures, not stool communities. Include only when the deposit also holds bulk stool shotgun runs; otherwise treat as `assay_other_nonshotgun` with a note, and cap confidence ≤0.6.
* **Sibling deposits of one cohort.** When a paper documents under-3 patients across several ENA deposits, the verdict for each deposit depends on which patients it holds; without per-sample ages commit `uncertain`, not `exclude` — and re-check siblings when one deposit is included.
* **Meconium ≠ shotgun.** Meconium/newborn deposits are disproportionately 16S; verify library strategy and depth before including on the age signal alone.

## Output contract

One row per (record, slot). Required keys:

```
record_id, slot, value, value_unit?, outcome, confidence (0-1), reason_code?,
evidence: [{source, quote}], evidence_limited_to?, model, note?
```

`outcome` values:
* `included` / `excluded_deterministic` / `excluded_llm` — triage verdicts
* `resolved_from_raw` — value lifted from a submitter-provided field
* `predicted` — inferred from study text, sibling consensus, or cohort default
* `resolved_at_pipeline` — deterministic pipeline already committed it; leave alone unless
  validation fails
* `unsure_adjudicated` — replicate disagreement sent to the adjudication queue
* `sentinel_no_evidence` — Rule 3 refusal; the deliverable for the curator
* `validator_rejected` — Rule 7 failed; validator name recorded in `note`

## Human steering across runs

Before judging any record set, read `DECISIONS.md` in the working directory if it exists — it
holds the curator's directives from earlier runs — and apply `overrides.tsv`
(`record_id, slot, value, reason`) as final. Never re-derive a value that has an override.

## Helpers (kernel.py)

`REASON_CODES`, `SOURCE_PREFIXES`, `validate_reason_code`, `validate_evidence`, `age_to_days`,
`validate_age`, `validate_accession_seen`, `find_accessions`, `sentinel_row`, `validate_row`.

## Per-sample extraction rules (added 2026-09-25, from the extraction pilot and audits)
Routes and precedence: R1 archive attributes / sample-name conventions > R2 supplementary tables > R3 paper text (group scope) > R4 abstract or ENA description (group scope, confidence ≤0.5, evidence_limited_to_abstract=1). Conflicts are adjudicated per (study, field, value-pair) pattern, not per sample.
1. **Pooled multi-study tables** count as paper.supp.table evidence for a study when ≥20 rows match its exact run/sample accessions (confidence cap 0.75, ranked below own-data tables). Fuzzy/token ID matches keep the ≥50 % gate. One source table per study × field; never majority-vote across tables with different semantics.
2. **Ranges, thresholds and lists are not values.** "0–1 month", "prior to 34 weeks", "collected at 3, 4, 6 and 12 months" never become age/GA values; a `term` verdict from a criterion needs ≥37 weeks; a list of collection ages may feed timepoint_label only.
3. **Boolean feeding columns** (`is_bf`, `breastfed`, `started_solids`) do not determine feeding_mode; "predominantly/mostly human milk" is not `mixed`.
4. **Group statements (R3/R4)** must pass the consistency check against per-sample values (drop when >20 % disagreement on ≥5 samples) and must not be drawn from: eligibility/exclusion criteria ("X were excluded", "not an exclusion criterion"), care setting or site policy (NICU stay, "not routinely prescribed", protocols/guidelines), "healthy infants/newborns/twins" (never implies term), summary words (predominantly, mostly, most, common, median, mean), a subgroup or a single case applied cohort-wide, maternal pregnancy-week sampling (not GA at birth), antiretrovirals (not antibiotics), or absence of unrelated illness (not nec_status=no). Every distinct group statement is audited (Opus checklist) before expansion.
5. **Unitless numeric age attributes** resolve only by U1 sibling attribute agreement, U2 unique admissible unit over the study distribution, or U3 a paper quote stating the unit; otherwise sentinel. Compact tokens in sample names (D6, M4, 6m) are timepoint labels, not ages, unless the study's own attributes confirm the unit. Explicit unit tokens (DOL 25, day 7, PND) take precedence over subject ordinals ("Infant 1").
6. **Parent-questionnaire attributes** (`antibiotic_history`, `probiotic_frequency`, "in the past year") are respondent history, not infant exposure, unless the key names the infant. `host_age` in weeks on a neonatal deposit may be gestational — require a postnatal cue.
7. **antibiotic_exposure** = any antibiotics before or at sampling; record `antibiotic_current` separately when a source distinguishes. cMD's `antibiotics_current_use` is not truth for this field.
8. **Evidence source labels** for attributes are `sample.attr.<attr_key_norm>`; library names are `run.library_name`; sample-name conventions are `sample_id_pattern`. Quotes are trimmed to ≤12 words before validation, never padded.

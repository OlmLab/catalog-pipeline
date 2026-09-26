# SCALE-UP PLAN — from the infant gut catalog to all human shotgun metagenomes (all body sites, all ages)
*2026-09-26. Sizing numbers come from the tables already built for the infant catalog (enumeration v3 full run, frame-free sweep, Sandpiper 2.0.0 per-run summary); they are the measured starting point, not projections.*

## 1. What the measured universe looks like today
| Slice (ENA, METAGENOMIC WGS/WXS, public) | Studies | Runs | Note |
|---|---:|---:|---|
| Enumeration v3 taxon frame (all gut/feces/human-* taxa, incl. animal deposits) | 8,966 | 1,069,270 | current triage universe (9,579 with growth channels) |
| … of which a *human* taxon name (human gut/oral/skin/vaginal/… metagenome) | 3,101 | 630,899 | 536,538 BioSamples |
| — gut / feces | 1,823 | 466,928 | infant catalog took 389 studies / 174k runs of this |
| — oral / saliva | 217 | 39,217 | |
| — respiratory (nasopharyngeal, lung, sputum, tracheal, nasal) | 217 | 16,715 | |
| — skin | 82 | 32,710 | |
| — vaginal / urogenital | 77 | 39,268 | |
| — blood / tissue / bile | 74 | 7,765 | |
| — milk | 17 | 4,648 | |
| — generic "human metagenome" only (site unknown) | 597 | 91,934 | needs site classification |
| Generic non-human-specific taxa in the frame ("gut metagenome", "metagenome" …) | ~5,800 | ~440k | mixture of animal and human deposits — the infant triage already excluded most as non-human |
| Frame-free sweep: human-signal studies under blank/off-frame taxa | 442 | 54,214 | grows ~150 studies/month |
| Sandpiper 2.0.0 runs with a "human …" organism | — | 329,822 | 240k human gut, 42k generic human, 12k oral, 7.7k skin, 2.5k nasopharyngeal, 2.5k vaginal, 1.6k lung, 1.4k blood |

**Working estimate for "all human shotgun metagenomes"**: 4,000–6,000 studies, 700k–900k runs, ~600k BioSamples (vs 389 / 174k / 154k now) — about 4–5× the current catalog in samples but 10–15× in studies, because the infant slice is dominated by a few very large cohorts.

## 2. What changes conceptually
1. **Triage becomes classification, not inclusion.** The question per study is no longer "infant gut, yes/no" but: human? (host) · which body site(s)? (controlled vocabulary anchored to UBERON) · which population(s)? (life stage; healthy/disease; special populations) · assay (shotgun DNA vs amplicon/RNA/isolate) · access (open/controlled). A study can carry several sites and life stages with per-sample resolution where the archive supports it. Exclusion is reserved for non-human, non-metagenome and non-shotgun.
2. **Two tiers of product.** *Registry tier* — every human shotgun metagenome study and run, with archive-only metadata (route R1), Sandpiper profiles/QC, papers and authors. This is cheap (deterministic + one Sonnet classification pass per study) and immediately useful. *Curated tier* — per-scope deep extraction (R2–R4 fields) done scope by scope, prioritised by sample count and user demand. The infant gut catalog is the first curated scope.
3. **Field packs.** *Core pack* (all scopes): body_site (+ UBERON id), age (continuous days + life-stage bin: neonate/infant/child/adolescent/adult/elderly), sex, country/geo_subregion, health_condition, antibiotic_exposure, medication, subject_id/timepoint, sample_unit. *Scope packs*: infant (delivery, feeding, preterm, GA, birth weight, NEC, HMO, maternal antibiotics — the current 12); adult gut (BMI, diet pattern, disease/IBD/T2D/CRC, PPI/metformin, stool consistency); oral (site: saliva/plaque/subgingival, periodontal status, caries, smoking); vaginal/urogenital (CST, pregnancy status, menstrual phase, contraception); skin (site, moisture class, condition); respiratory (site, disease: CF/COPD/pneumonia, ventilation). Each pack is a vocabulary file plus prompt fragments, not new code.
4. **Sample unit** stays BioSample-by-default with run-level rows for pooled-subject deposits (the rule and code exist).
5. **Taxonomy** via Sandpiper for every run (join is free); body-site classification can be cross-checked against composition (e.g. a "gut" study whose profiles are Cutibacterium-dominated is skin), which becomes a second QC signal in triage.

## 3. What changes structurally (following the architecture review)
* **Skills**: split `infant-curation-rules` → `catalog-curation-core` (evidence rules, validators, routes, audit checklists, traps common to all scopes) + `<scope>-vocabularies`. `infant-catalog-harvest` → `catalog-harvest` (already scope-agnostic apart from the taxid table).
* **Projects**: one project per scope (gut-adult, oral, skin, vaginal/urogenital, respiratory, other/tissue), plus one *registry* project that owns enumeration, classification, Sandpiper and the top-level site. Each scope project holds only its own grants/credentials and memory. All share the pipeline repo (`config/scope.yaml` selects vocabularies, packs and the triage prompt).
* **Repos/site**: `catalog-pipeline` (code, unchanged shape), one `human-metagenome-registry-data` repo (registry tier tables), one data repo per curated scope, and **one GitHub Pages repo per scope** (`<scope>-catalog`, e.g. the existing `infant-gut-catalog`), each built by the same generator with a scope config and each staying well under the Pages limits (1 GB published site, 100 MB/file; the infant site is already 293 MB incl. the 67 MB zip, so a single combined site is not an option). A small **registry index site** (`human-metagenome-registry`: all studies, body-site facets, authors, universe, links into every scope site) replaces the earlier "federated site" idea; its explorer works on a run-level summary table, never on per-sample fields (R1-12).
* **Pipeline changes**: (a) enumeration = frame-free sweep + BioSample-attribute sweep only, over `library_source=METAGENOMIC` WGS/WXS (plus misfiled GENOMIC under human taxa), no taxon frame; (b) human-signal rule stays as the pre-filter, followed by a Sonnet ×2 classification (host, sites, life stages, assay) with Opus on disagreement — same machinery as the current triage; (c) extraction is **route-gated**: R1 (archive attributes) for every sample of every study automatically; R2 (supplementary tables) automatically for studies with an open supplement inventory; R3/R4 (prose) only for studies above a sample threshold (e.g. ≥50 samples) or requested via the site; (d) audits unchanged (validator on every row; Opus statement audit; blind Sonnet audit sample per release).

## 4. Phasing
| Phase | Content | Deterministic / LLM | Estimate |
|---|---|---|---|
| S0 Prep (2–3 weeks) | Skill split; `config/scope.yaml`; registry project; body-site/life-stage vocabularies with UBERON ids; classification prompt + 200-study gold from the current universe (already judged human/non-human) | mostly deterministic; gold reuse | <1M tokens |
| S1 Registry universe | Frame-free + BioSample sweeps over all ENA; human-signal pre-filter; Sonnet×2 + Opus classification of ~6–8k candidate studies | LLM **4.0–7.2k tokens/study** (measured aggregate 4,000; component build-up 2×(1,150+4,900/4) Sonnet + 20 % Opus + Haiku share — `config/budgets.yaml`, `scripts/budget_calc.py`) | **24–58 M tokens**; **12–29 leaf frames at the 2.0 M/frame hard cap, 80–193 at the 300 k soft cap** (the dispatch unit); at 10–15 concurrent leaves ≈ 3–6 days wall |
| S2 Registry tier data | R1 for all ~600k BioSamples (attribute harvest ~30M attribute rows; ENA XML + NCBI efetch), Sandpiper join for ~800k runs (bulk snapshot already an artifact), papers + authors for all studies, registry site | deterministic except attribute-key normalisation | 1 week wall (harvest-bound); **Haiku normalisation cost NOT measured** — the infant build normalised distinct attribute keys, not rows; S0 must run a 10k-row pilot and record tokens/1k distinct (key, value) pairs in `budgets.yaml` before this line gets a number |
| S3 Curated scopes, in order | 1. adult/all-age gut (largest: ~1,400 studies, ~300k runs) → 2. oral → 3. vaginal/urogenital → 4. skin → 5. respiratory → 6. blood/tissue/other. Per scope: R2 automatic, R3/R4 gated, audits, gold where an external curation exists (curatedMetagenomicData covers adult gut; HMP/other consortia for oral/skin/vaginal) | infant extraction cost 14M for 174k runs → gut-adult ≈25–35M with gating; others 3–8M each | 60–90M tokens total; 2–4 months elapsed at one scope at a time |
| S4 Continuous | Monthly re-sweep (all scopes), Sandpiper refresh on new Zenodo version (Curator stage 1b/1c), findings + confirmations from the websites | infant scope alone: **0.8 M typical, ≤ 1.5 M high per month** (RUNBOOK §8 = NEXT_STAGE §7 = `budget_calc.py`); each additional curated scope adds its own cycle of the same shape scaled by its monthly new-study count | steady state |

Order rationale: gut-adult has the most samples and an external gold (cMD); oral and vaginal have consortium metadata standards (HMP, MOMS-PI) that make R1/R2 rich; skin and respiratory are smaller and prose-heavy.

## 5. Risks specific to scale
| Risk | Mitigation |
|---|---|
| Body-site ambiguity for the 597 generic "human metagenome" studies and mixed-site cohorts (HMP) | per-sample site from attributes (body_site, isolation_source, UBERON terms) before study-level defaults; Sandpiper composition as tie-breaker; "mixed" allowed at study level |
| Life-stage leakage (adults labelled infant or vice versa) | age_scope logic from the data-model fix generalises; role default unknown; explicit `age_evidence` column |
| Extraction cost explosion | route gating; per-scope budgets in `config/budgets.yaml`; stop rules; registry tier first |
| Attribute harvest volume (~30M rows) | parquet partitioned by study; harvest cache on host filesystem (`~/catalog/cache/`), not artifacts |
| Static-site limits (100 MB/file, 1 GB published site) | one Pages repo per scope + a registry index site (§3); run-level summaries only in the registry explorer; deploy from Actions (no history growth) |
| Gold scarcity outside gut | consortium metadata as gold (HMP, MOMS-PI, TEDDY-like), plus the website confirm queue |
| Controlled-access studies (dbGaP/EGA) | registry lists them with access tier; no per-sample metadata beyond public attributes |

## 6. First concrete steps (if approved)
1. Skill split and `config/scope.yaml` (2 days).
2. Registry project + S1 classification run on the current 9,579 + frame-free universe as a dry run (reuses existing triage verdicts as gold: 389 include / 9,138 exclude already judged human/non-human).
3. Registry-tier site as a new top-level section of the current site (body-site facets, authors), so the infant catalog becomes one scope inside it rather than a separate product.


## 7. Budget derivation (R1-12; recompute with `python scripts/budget_calc.py`)

| quantity | value | derivation (config/budgets.yaml) |
|---|---:|---|
| Sonnet x2 per study | 4,750 | 2 x (1150 + 4900/4) |
| Opus share per study | 1,580 | 0.20 x (3000 + 4900/1) |
| Haiku screen share per study | 898 | 4900/40 + 775 proxy (per-item screen cost unmeasured) |
| **triage tokens per judged study** | **4,000–7,228** | measured aggregate vs component build-up |
| S1 classification of 6,000–8,000 studies | 24–58 M | studies x per-study |
| S1 leaf frames at the 2.0 M hard cap | 12–29 | ceil(tokens / cap) |
| S1 leaf frames at the 300 k soft cap | 80–193 | ceil(tokens / soft cap) — the dispatch plan |
| monthly triage (108 judged, max 143) | 0.43–1.03 M | judged x per-study |
| monthly extraction (5.7 includes, max 11) | 0.28–0.55 M | includes x 50,000 |
| **monthly cycle total** | **0.8 M typical, ≤ 1.5 M high** | cycle_tokens_expected |
| monthly leaf frames at the soft cap | 3–5 | ceil(cycle / 300 k) |
| new human-signal studies / month | 146 (111–180) | per_cycle_expected |
| deterministic auto-excluded / month | 38 | per_cycle_expected |
| new included / month | 5.7 (2–11) | per_cycle_expected |

All figures above derive from `config/budgets.yaml`; the S1 line of §4 uses the per-study range and the two frame caps; NEXT_STAGE.md §7 and RUNBOOK §8 use the monthly lines.

# NEXT STAGE — organisation, delegation and roadmap for the Infant Gut Shotgun-Metagenome Catalog
*Written 2026-09-26 after two independent plan reviews (Reviewer_A_REVIEW.md — architecture/operations; Reviewer_B_REVIEW.md — data/science) and the Phase 2 build tracks. Companion documents: SCALE_UP_PLAN.md (all human metagenomes), docs/RUNBOOK.md and REPO_REPORT.md (pipeline repo), SANDPIPER_REPORT.md, DATA_MODEL_FIX_REPORT.md.*

## 0. What you asked for, restated
One person. You audit the metadata by browsing a website that is simultaneously the public resource. You want Claude sessions to do as much of the maintenance as possible — rebuilding, publishing to GitHub Pages, new curation rounds, later expansion beyond infants — including credentials that let a session publish without you. This document says how to set that up, why, and what the alternatives were.

## 1. Recommendation in one page
| Question | Recommendation | Why (see §) |
|---|---|---|
| One project or several? | **One project for the infant catalog + its website.** New **project per scope** (e.g. adult gut, skin, vaginal) when you expand — sharing the pipeline repo and the core skills, not the memory or the credentials. | §2 |
| Different agents? | **Three specialist profiles inside the project**: **Curator** (runs cycles; may delegate), **Auditor** (read-only explainer; no grants, no credentials), **Release Engineer** (package + site + publish; the only profile holding the GitHub token and the `~/catalog/` write grant). | §2 |
| Where do files live on your Mac? | One folder **`~/catalog/`**, granted read-write once, with three git clones inside: `microbiome_repo-pipeline/` (code), `microbiome_repo-data/` (published tables, findings), `microbiome_repo/` (the Pages site, generated only), plus gitignored `cache/` and `external/`. | §3 |
| How does a session publish without you? | Fine-grained GitHub PAT stored in **Customize → Credentials**, scoped to the two public repos with `contents: write` only; **rulesets on `main`** (no force-push, no deletion); the agent pushes **`release/<version>` branches and `data-vX.Y.Z` tags**; **GitHub Actions** deploys Pages and attaches large files as Release assets after a smoke test. Rollback = redeploy the previous tag. | §4 |
| How do you audit while browsing? | Every study page and every value in the explorer gets **Flag / Confirm** buttons that open a pre-filled GitHub Issue; the Curator converts labelled Issues into `audit/findings/*.csv`; `apply_findings.py` re-validates and applies them with decision stage `auditor_review`; the site shows **decision history** and **superseded values**. | §5 |
| Taxonomy (Sandpiper)? | Two tiers: **summary columns + top-15 genera per sample + per-study composition panels on the site**; full run × taxon profiles as a Release/Zenodo asset. GTDB-defined indicators, coverage summed across runs then normalised. Refresh when Zenodo publishes a new Sandpiper version. | §6 |

## 2. Projects and agent profiles
**Why one project.** The website is generated from the catalog's tables and needs the same artifacts, memory rows and skills the curation work produced; a separate "website project" would either duplicate ~10 GB of artifacts or read across projects on every build. Memory recall also works best when a project's memory describes one scope.

**Why split by scope later.** Project memory is already ~150 rows over ~90 sessions. An adult-gut or skin catalog would add a different universe, different vocabularies (no delivery mode, different age semantics) and different traps; mixing them degrades recall and widens the blast radius of the grants and tokens (an rw grant and a PAT for the infant repos should not be inherited by another scope). Before expansion (**planned, S0 of SCALE_UP_PLAN — `docs/EXPANSION.md` and `config/scope.yaml` do not exist yet**): split the `infant-curation-rules` skill into `catalog-curation-core` (evidence rules, validators, routes, audit checklists) and `infant-vocabularies`; put scope in `config/scope.yaml`; fork the pipeline repo config, not the code (see `docs/EXPANSION.md` in the repo).

**Profiles** (two created in this phase as `CATALOG_AUDITOR` and `RELEASE_ENGINEER` — the name `AUDITOR` is reserved by a built-in profile; the Curator role is the current default profile with these docs loaded. Note: the platform did not allow creating them with unrestricted skill/connector access from this session, so both carry an explicit skill list — infant-curation-rules, infant-catalog-harvest, self-awareness (+ figure-style, customize for the Release Engineer); add skills via `host.agents.update` when new ones are published):
* **Curator** — the current pipeline role. Runs the monthly cycle from RUNBOOK.md: re-sweep → triage new candidates (Sonnet ×2 + Opus) → extraction for new includes → hand results to the Release Engineer. Needs delegation enabled for fan-outs; budgets in `config/budgets.yaml`.
* **Auditor** — read-only. Explains any paper / BioProject / sample / cohort from the tables (universe channel, verdict + evidence + history, papers, coverage, blockers) and writes findings rows. No host grants, no credentials, never edits artifacts.
* **Release Engineer** — deterministic: rebuild package (semver), VERSION.json, site; run verify; sync to `~/catalog/`; push `release/<version>` + tag; watch Actions; report. Holds the PAT and the `~/catalog/` grant. Never runs LLM curation.

**Memory hygiene.** One consolidation pass to ≤40 durable rows (decisions, conventions, canonical artifact ids); per-run facts move to CHANGELOG/CYCLE_LOG in the repo.

## 3. Filesystem layout (`~/catalog/`, granted rw once)
```
~/catalog/
  microbiome_repo-pipeline/          # code, config, tests, docs, site_generator/, src/catalog/sandpiper/, src/catalog/authors/  (GitHub: OlmLab/microbiome_repo-pipeline)
  microbiome_repo-data/   # package tables (≤50 MB each), audit/findings/, reports/, VERSION.json; tags data-vX.Y.Z  (public)
  microbiome_repo/        # generated site only; Pages deploys from Actions  (public, existing repo)
  cache/                     # harvest_cache untarred (~10 GB), gitignored — never in git, never an artifact version per run
  external/sandpiper/<ver>/  # Zenodo bulk snapshots with sha256
```
Rules the agent follows there: no `rm -rf`, no `rsync --delete` outside `git clean` inside a clone; `.gitignore` covers `.DS_Store`, caches. Large outputs (sqlite 200 MB, release bundle, full Sandpiper profiles) never enter git — Actions attaches them to Releases.

Today's `~/Downloads/site` clone becomes `~/catalog/infant-gut-catalog/` (move the folder; the remote stays).

## 4. Publishing without you — credential design
What you set up once (≈20 min):
1. **Organisation policy**: OlmLab → Settings → Third-party access → Personal access tokens → allow fine-grained PATs (approval optional).
2. **Rulesets** on `main` of both public repos: block force-push and branch deletion; require linear history.
3. **Pages source = GitHub Actions** on `microbiome_repo` (Settings → Pages). The repo's `deploy-pages.yml` (shipped in the pipeline repo) builds the artifact from `release/*` merges or `site-v*` tags after `verify.yml` passes.
4. **Fine-grained PAT**: resource owner OlmLab; repositories `microbiome_repo` and `microbiome_repo-data`; permissions Contents: read/write, Metadata: read; expiry 1 year (calendar reminder). Store it in **Customize → Credentials** as `github` (token). The agent uses it only in cells that declare it, via an in-memory git credential helper — it is never written to disk, artifacts or remotes.
5. Optional: Zenodo–GitHub integration on the data repo → a DOI per Release.

What the agent then does: commit to `release/<version>`, push, tag `data-vX.Y.Z`; Actions runs link check + DuckDB parquet read + Playwright explorer smoke; on success deploys Pages and attaches Release assets; on failure opens an Issue and does not deploy. Rollback: re-run the deploy workflow on the previous tag. Things that stay manual: Pages settings, custom domain, token rotation, org policy.

Why not the alternatives: agent-uploaded Release assets are impossible from sessions (`uploads.github.com` is non-grantable); committing the generated site to `main` grows history ~60 MB per rebuild (already 143 MB after two pushes) and makes rollback a 2,000-file revert; keeping you as the pusher is the current fallback and remains valid whenever no credential is configured.

## 5. Auditing through the website
* **Provenance on every page**: package version, build SHA, build date (VERSION.json); per-table row counts and hashes on Downloads.
* **Decision history** on study pages (every triage stage, verdict, confidence, model, quote) and **value history** in the explorer detail (superseded, rejected, audit-dropped values with reasons).
* **Flag / Confirm** buttons → GitHub Issue template with accession, field, current value, version. Labelled Issues → `audit/findings/YYYY-MM-DD.csv` → `apply_findings.py` (re-validates with the skill validators; stage `auditor_review`; diff report) → next release. The read-only Auditor profile remains for deep explanations.
* **Truth set through the site**: a per-release `truth_set_tasks.csv` (stratified by route × field) rendered as a "confirm" queue; your confirmations feed human precision per field × tier onto the Fields page — the only evaluation route for the exposure fields (probiotic, HMO, NEC, birth weight, maternal antibiotics) that have no external gold.
* **Defaults that prevent misreading**: explorer results and exports apply the README rule by default (R1/R2 any confidence; R3/R4 ≥0.5), show `<field>__scope`, label run-unit rows as ENA runs, and the dictionary states that confidence is an engine tier, not a calibrated probability.

## 6. Sandpiper (taxonomy) integration
**Result of the join (Sandpiper 2.0.0, GTDB R232, Zenodo 20419175; details in SANDPIPER_REPORT.md).** 87,125 of 174,022 catalog runs (50.1 %) and 79,473 of 154,206 sample units (51.5 %; 77,191 infant-scope) are profiled; 22 studies fully, 280 partly, 87 not at all. Misses are deterministic and named per run: runs <100 Mbp (12.4 %), published after the snapshot horizon 2026-03-22 (10.2 % — the per-run delta route covers these), Illumina runs simply absent from the crawl (13.8 %, mostly ENA-only ERR deposits), the controlled-access TEDDY study (7.6 %), non-Illumina platforms (5.8 %; Sandpiper 2.0.0 profiles Illumina only). The bulk file already carries *filled* coverage; the conversion was validated bit-exactly against Sandpiper's own with-extras download for 4 runs. Per-run JSON endpoints exist under `/api/` (condensed_csv_with_extras, metadata with QC flag definitions) — the monthly delta route, ≤2,000 runs/cycle, cache-through. Run concordance flagged 99 multi-run BioSamples (BC>0.5) — all class C, mostly VLP vs bulk libraries in one virome study; none changed, queued for review. Sizes: full profiles 10.4 M rows (off-site asset); top-genera 1.05 M rows and sample summary are on-site.
Design: join on run accession; Zenodo bulk snapshot (v2.0.0, GTDB R232) as the primary source, per-run pages only for monthly deltas (capped, cache-through); aggregation to the catalog sample unit by summing unfilled coverage across a sample's runs, then fill and normalise; unassigned fractions kept explicit; indicator taxa defined in GTDB terms (Bifidobacterium genus + species table; Bacteroidaceae with Bacteroides/Phocaeicola; an explicit Enterobacterales genus sum; Lachnospiraceae; Lactobacillaceae) and named `sp_ra_*` to avoid NCBI/GTDB confusion; QC flags (SPF, known-species fraction, low depth, non-metagenome/RNA/synthetic) stored per run and surfaced to the Auditor queue — never auto-changing a verdict. On the site: summary columns, a top-15-genus table (~8 MB) loaded on demand, per-study composition panels; full profiles as a Release asset. Refresh when Zenodo publishes a new Sandpiper concept version (expect 1–2/yr); Sandpiper is CC-BY — cite Woodcroft et al. 2025, Nat Biotechnol, and Zenodo 20419175.

## 7. Roadmap and cost per cycle

One table, shared with RUNBOOK §8 and `config/budgets.yaml` (recompute: `python scripts/budget_calc.py`; R1-12). Volumes are the
measured 2025-09..2026-08 monthly means from `universe_studies_all.first_public_min`.

| RUNBOOK stage | Who | Expected volume / month | Tokens | Wall | Delegation |
|---|---|---|---|---|---|
| 0 preconditions (`bootstrap.py`, exit 4 on missing inputs) | Curator | — | 0 | 10 min | no |
| 1 frame-free re-sweep (`make resweep`) | Curator | ≈ 146 new human-signal studies (111–180), of which ≈ 38 auto-excluded → **≈ 108 to judge** | 0 | 20–40 min | no |
| 1b Sandpiper delta (`make sandpiper-delta`) · 1c snapshot refresh on a new Zenodo version · 1d authors | Curator | runs added since last package; 1c ≈ quarterly | 0 | 40 min · 70 min · 25 min | no |
| 2 triage: Haiku screen (if > 150) → Sonnet ×2 → Opus on ≈ 20 % → literature check | Curator | ≈ 108 judged (max 143) | **0.43–1.03 M** (4.0–7.2 k/study) | 1.5 h | **yes** — 2–4 leaf frames at the 300 k soft cap |
| 3 extraction R1–R4 for new includes | Curator | ≈ 6 includes (2–11) | **0.28–0.55 M** (50 k/study) | 2–3 h | **yes** — 1–2 leaf frames |
| 4 findings: `make ingest-issues` → `make findings` (confirm rows → truth set) | Curator | as Issues arrive | 0 | 30 min | no |
| 5–6 package (deterministic zip), site, verify | Release Engineer | — | 0 | 30 min + Actions | no |
| 7 publish `release/<semver>` + tags; Actions deploys | Release Engineer | — | 0 | 10 min | no |
| **cycle** | | | **≈ 0.8 M typical, ≤ 1.5 M high; 3–5 leaf frames** | **≈ 5 h agent time** | |

Stop rule: >300 new candidate studies or any validator-sync failure → ask the owner. Log actuals in `docs/CYCLE_LOG.md`.

Longer roadmap: (1) BioSample-attribute + frame-free sweeps as the standing intake; (2) submitter outreach for the ~42k samples whose tables need submitter keys (pack ready); (3) exposure-field truth set via the site; (4) expansion scopes as new projects, one Pages repo per scope plus a registry index site (SCALE_UP_PLAN §3); (5) methods paper.

## 8. Risks
| Risk | Mitigation |
|---|---|
| Prompt-injected agent publishes bad content | Rulesets, release-branch-only pushes, smoke-gated deploy, rollback by tag; agent never touches Pages settings |
| Token expiry / org policy change | Yearly rotation reminder in RUNBOOK; publish falls back to human push |
| Harvest cache loss (working_data artifact, single copy) | Per-release snapshot copies + sha256; untarred copy in `~/catalog/cache/` |
| Model id drift | `config/models.yaml` resolves roles at runtime via `host.list_models()`; no literal ids |
| Sandpiper taxonomy drift (GTDB releases) | Version columns on every row; panels computed within one release |
| Memory sprawl | Consolidation pass; durable facts in repo docs |

## 9. Repository and runbook (delivered)
`pipeline_repo.zip` (129 files; REPO_REPORT.md, docs/RUNBOOK.md): 66 producing scripts collected from the artifact store with version ids and sha256 in `config/inputs.json`; `config/models.yaml` resolves model roles at runtime (8 scripts had literal model ids replaced); `apply_findings.py`, `make_version.py`, `bootstrap.py`; 77 tests pass (determinism test xfail until the generator v2 lands); workflows verify/deploy-pages/release and the `catalog-finding` Issue template; SECURITY.md, ARCHITECTURE.md, DATA_LAYOUT.md, CHANGELOG v1–v11. Measured cycle expectation from the universe's first_public dates: ≈146 new human-signal candidate studies and ≈6 new includes per month, ≈0.8 M tokens per cycle. Known gaps: 13 stage modules are exec-style scripts (not importable) and the 9.75 GB harvest cache is referenced by artifact id only.

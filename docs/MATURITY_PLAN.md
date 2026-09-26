# MATURITY PLAN — a versioned, community-maintained catalog (GTDB-style releases + user contributions)
*2026-09-26. Design proposal; nothing here is built yet except where marked (exists). Numbers cited come from the v1.2.1 package and the extraction reports.*

## 1. Goal
Turn the catalog from a series of ad-hoc data packages into a **release-versioned reference resource** where (a) every value's history is inspectable and every past release is reproducible and citable, and (b) outside users can see what work is missing, contribute the missing inputs (chiefly supplementary tables), and see their contribution enter the next release with attribution.

## 2. Versioning model (what GTDB does, adapted)
GTDB publishes numbered releases (R207, R214, R220 …), each frozen, each with a DOI, with a changelog and per-genome "history" showing taxonomy changes across releases. The catalog equivalent:

| Element | Design | Status |
|---|---|---|
| **Release identifier** | `R<YYYY>.<n>` (e.g. R2026.1) for the *catalog release*; semver for the data package format (`1.2.1` = schema/columns). A release = package + site + SQLite + full Sandpiper profiles, all carrying the same `release_tag`. | package semver + VERSION.json exist; release tag field exists |
| **Immutability** | A release is never edited. Fixes go into the next release. Each release archived as a GitHub Release (assets) **and** a Zenodo deposit (DOI, via the GitHub–Zenodo integration on the data repo); site footer shows release + DOI. | GitHub Release workflow exists (not yet run); Zenodo integration = owner step |
| **Stable identifiers** | Catalog entities keyed by archive accessions (BioProject, BioSample/run, PMID) — stable by construction. Cohort ids (`COH0002`) and finding ids must become stable: never renumbered, only deprecated (`status=deprecated, merged_into=`). | cohort ids exist; deprecation rule not yet enforced |
| **Bitemporal tables** | Every fact row carries `release_added` and `release_retired` (null = current). `sample_determinations`, `study_triage`, `cohorts`, `paper_study_links`, `sandpiper_*` all get these two columns. "Current" = `release_retired IS NULL`. The *full* table (all releases) is the archive; the package ships current + `value_history`. | value_history (45,886 rows) and study_verdict_history (32,231 rows) exist as the seed; columns not yet on the main tables |
| **Per-entity history views** | Study page: verdict timeline across releases (exists as "Decision history" within one release). Sample detail: value timeline per field with the release in which each value was added/retired and why (finding id, route change, Sandpiper version). Add a **"changed since R…" page** listing studies/samples whose values changed, generated from the bitemporal table. | partly exists |
| **Release diff report** | Auto-generated `RELEASE_NOTES_R2026.n.md`: new/removed studies, samples, per-field coverage delta, verdict flips, contributions applied, Sandpiper snapshot version, gold metrics before/after, token cost. | CHANGELOG exists (hand-written); generator to write |
| **Reproducibility** | `config/inputs.json` pins every input by artifact id + sha256; `VERSION.json` hashes every output; deterministic package zip and site build (two builds byte-identical). A release can be rebuilt from the pipeline repo at the release tag. | exists (repo v3) |
| **Schema versioning** | `schema.json` + DATA_DICTIONARY carry `schema_version`; breaking column changes bump the package major; migration notes per release. | partial |
| **Citation** | Site "Cite" box per release: catalog DOI (Zenodo), plus the mandatory upstream citations (ENA/INSDC, Sandpiper/SingleM, curatedMetagenomicData for gold). | to add |

**Release cadence.** Monthly *point releases* (re-sweep + contributions applied; automatic), and a yearly *major release* with a methods paper–style report and a re-run of all audits. Everything in between is "unreleased main" in the data repo, visible on a staging site (`staging/` path of the Pages site or a second Pages repo) so the owner audits changes before they become a release.

## 3. Community contribution system
### 3.1 What users can do (v1 scope)
The single highest-value contribution is the one the pipeline cannot do itself: **supply the per-sample supplementary table (or the key that joins it to archive accessions)** for studies where R1/R2 metadata is missing. The measured backlog: 170 included studies have no PMC-linked supplementary table at all, and 77 studies (~42k samples; TEDDY alone 12k) have tables keyed by identifiers absent from the archive — these need the submitter's key file. A user who knows the study (an author, a lab member, a reader of the paper) can often locate or produce that file in minutes.

Contribution types, in priority order:
1. **Upload a per-sample table** (CSV/TSV/XLSX) for a named study, with a note on where it came from (journal supplement URL, author correspondence, own lab records).
2. **Upload an ID key** (sample name ↔ BioSample/run accession) for a study whose tables are unjoinable.
3. **Point to a paper** (PMID/DOI) for an unlinked study.
4. **Flag / confirm** a value (already designed: Issue template + `apply_findings.py`).
5. **Claim a task**: mark a worklist item as "working on it" to avoid duplicate effort.

### 3.2 The "work needed" view (site)
A `contribute/` section generated from the tables:
* **Worklist**: studies ranked by (samples × missing fields), each with: what is missing (age? delivery?), why (`no_supplement_found`, `tables_unjoinable: keyed by subject id`, `paywalled`), the linked papers, the ENA/NCBI links, and a **Contribute** button. The `extraction_worklist.csv` (429 studies) and the recoverability tiers are the seed.
* Per-study "what would unlock this" text from the recoverability track ("per-sample table keyed by run accession", "key mapping T1_S23 → SRR…").
* Leaderboard/attribution page (opt-in display name or institution; e-mail never shown).

### 3.3 Architecture (a static site cannot receive uploads)
GitHub Pages is static; uploads need a small trusted backend. Recommended minimal stack (all free-tier, no server to maintain):
* **Identity**: magic-link e-mail sign-in restricted to allowed domains (`.edu`, `.ac.uk`, `.edu.au`, … allow-list in config). Implemented with a hosted auth provider (Cloudflare Access one-time PIN, Auth0/Supabase magic links) or a ~100-line Cloudflare Worker: user enters e-mail → signed token e-mailed → link back sets a short-lived cookie. The **verified e-mail is the provenance source** recorded with every contribution (`evidence_source = contributor:<sha256(email)>`, display as domain + optional name).
* **Upload endpoint**: Cloudflare Worker (or Vercel/Netlify function) accepting multipart upload ≤50 MB, virus/size/type checks, writing to **object storage** (Cloudflare R2 / S3) under `incoming/<date>/<study>/<uuid>/` with a JSON manifest (study, uploader hash, source URL, note, timestamp). The Worker also opens a GitHub Issue (label `contribution`) via the API so the queue is visible and auditable.
* **Alternative with zero custom backend**: contributions as GitHub Issues with file attachments (GitHub hosts the file; requires a GitHub account rather than an .edu e-mail). Good as a fallback; loses the .edu gate.
* **Nothing executes user code**: uploads are data only; parsing happens in the pipeline with the same table gate used for PMC supplements.

### 3.4 Daily/weekly processing ("the daily thing")
1. **Ingest (deterministic, GitHub Actions cron, daily)**: `ingest_contributions.py` lists new objects in `incoming/`, validates (readable table, ≤N columns, no executable content), moves to `staging/`, and runs the **existing R2 gate** (`r2_supp_extract_v2.py` + `r2_rescue_map.py`): does the table's ID column map to the study's own BioSamples/runs/library names/aliases (or via an uploaded key)? Output per upload: `mapped_rows`, `fields_detected` (header classification is the Haiku step — run it in the Curator session, or keep a deterministic header dictionary first), and a verdict `accepted_for_review | unjoinable | duplicate_of_existing | rejected`.
2. **Curation (Claude Curator session, weekly or on demand)**: for accepted uploads run the normal extraction contract (validate_row on every value; route R2; `evidence_source = contributor_table:<upload_id>`; confidence per the R2 rules; conflicts with existing R1/R2 values go to the conflict queue, never silently overwrite). The owner sees a diff on the staging site.
3. **Release**: applied contributions enter the next point release with `release_added`, and the contributor's attribution appears on the study page ("Per-sample table contributed by <name/institution>, 2026-10-03").
4. **Feedback**: the Worker (or Actions) comments on the contribution Issue with the outcome and, if unjoinable, what is missing (e.g. "ids look like T1_S23; a key to SRR accessions is needed").

### 3.5 Trust and safety
* Provenance: every contributed value carries the upload id, uploader hash, and the file hash; the raw file is retained in storage for audit; contributor e-mails are stored hashed with a salted mapping in a private store, never in the public package.
* Gates: .edu allow-list; per-user daily quota; size/type limits; duplicate detection by file hash; the R2 gate rejects tables that do not map to the study's own accessions (the same rule that stopped pooled meta-analysis tables from producing false ages).
* Precedence: contributed tables are route R2 — they never override a per-sample archive attribute (R1); a contributor claiming an R1 value is wrong files a *finding*, which goes through `apply_findings.py` with Curator review.
* Licence: contributors agree that uploaded tables are redistributed under the catalog licence (CC-BY-4.0) or, if the source is a paywalled supplement, only derived values are published (table retained privately).
* Abuse: audit log of all uploads; owner can block a domain/hash; nothing is published without the Curator step.

### 3.6 Effort estimate
| Piece | Effort | Notes |
|---|---|---|
| Bitemporal columns + release tag on all tables; `make release` writing RELEASE_NOTES | 2–3 days | deterministic |
| "Changed since" page + per-sample value timeline | 1–2 days | generator |
| Zenodo DOI per release | 1 h owner setup | |
| contribute/ worklist pages | 1 day | from existing worklist + recoverability |
| Auth + upload Worker + R2 bucket + Issue creation | 2–3 days, ~$0–5/month | owner creates the Cloudflare account and DNS; agent writes the Worker |
| ingest_contributions.py + Actions cron + gate reuse | 2 days | reuses r2_supp_extract_v2 / r2_rescue_map |
| Curator weekly procedure in RUNBOOK; attribution rendering | 1 day | |

## 4. Order of work
1. Bitemporal tables and release notes (makes everything after it auditable).
2. Zenodo DOI and first numbered release R2026.1 from package 1.2.x.
3. contribute/ worklist pages (read-only; already useful — users can e-mail tables to the owner meanwhile).
4. Upload backend with .edu magic link; ingest cron; Curator weekly step.
5. Attribution and "changed since" views; then open to a wider domain allow-list.

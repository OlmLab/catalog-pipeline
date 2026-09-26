---
name: infant-catalog-harvest
description: "Cache-through harvesting helpers for the Infant Gut Shotgun-Metagenome Catalog: ENA portal enumeration (count/search with field lists), Europe PMC search / fullTextXML / supplementary ZIPs, NCBI eutils, Crossref, Semantic Scholar, bioRxiv JATS, all through one SQLite+blob HTTP cache (harvest_cache/) with per-call logging. Load when re-enumerating the ENA universe, refreshing the literature frame, or resuming a harvest from the saved harvest_cache.tar.gz working_data artifact."
---

# Infant catalog harvest

All outbound HTTP for the catalog goes through `harvest_lib.py` (project artifact
`b5eefacd-1a3b-4f48-a931-3b732fbad09e`; copy into the cwd and `sys.path.append(os.getcwd())`).
Every response is cached in `./harvest_cache/http_cache.sqlite` (url → status, bytes, blob_sha)
with bodies in `./harvest_cache/blobs/<sha[:2]>/<sha>`, and every call is logged to
`infant_metagenome_catalog.sqlite::harvest_log` with a `purpose` tag.

## Resume from the saved cache
```python
import tarfile; tarfile.open(host.artifact_path("<harvest_cache.tar.gz version id>")).extractall(".", filter="data")
import harvest_lib as HL; HL.cache_stats()   # entries / ok / err / bytes
```
The working_data artifact keeps only the latest copy; re-save it (`destination={"harvest_cache.tar.gz":"working_data"}`,
`version_of=`) after a fetch wave. ZIP blobs >20 MB may be stubs when disk was tight — check size before unzipping.

## Core calls (all return dicts: ok, status, body, from_cache)
* `HL.fetch(url, purpose=...)`, `fetch_json`, `fetch_text`, `fetch_many(urls, workers=6)`
* ENA: `HL.ena_count(result, query)`, `HL.ena_search(result, query, fields, limit=0, fmt="tsv")`
  — `result` in {study, read_run, sample}; field lists in `scope_constants.ENA_RUN_FIELDS` /
  `ENA_STUDY_FIELDS`. Batch accessions with `study_accession="PRJ..." OR ...` (10–20 per call).
* Europe PMC: `epmc_search(query, page_size=1000, cursor="*")`, `epmc_search_all`, `epmc_count`,
  `epmc_fulltext_xml(pmcid)`, `epmc_supplementary_zip(pmcid)` (≈15% of OA papers return HTTP 500
  for fullTextXML — record and move on; do not retry in a loop).
* NCBI: `esearch`, `esearch_all_ids`, `esummary`, `efetch`, `elink`, `sra_runinfo`.
* Literature graph: `crossref(doi=|query=)`, `s2_search`, `s2_refs`; preprints:
  `biorxiv_details(server, doi)` (rate-limits at ~70 calls/30 min → HTTP 429; pace it).

## Enumeration rules of thumb (learned 2026-09-18)
* ENA taxid for "human feces metagenome" is **2705415** (3007725 has 0 runs). "human gut metagenome"
  408170; generic "metagenome" 256318 has no host_tax_id — reachable only via literature.
* Enumerate the OTHER/Targeted-Capture adjudication slice for `tax_eq(9606)` too, not only for
  the metagenome taxa; 122 studies / 11k runs were missed otherwise.
* `library_source=METAGENOMIC AND library_strategy in (WGS, WXS)` is the primary slice;
  OTHER/Targeted-Capture go to adjudication; `age` is empty in ENA read_run for essentially all
  human runs — per-sample age must come from BioSample XML or supplements.
* Fixed overhead per ENA portal call is small; batch 10–20 study accessions per query.

## Accession mining (mine_accessions.py, artifact 30e5eec1)
Regexes for PRJ*/SRP/ERP/DRP, SRR/ERR/DRR, SAMN/SAMEA/SAMD, SRX/ERX, GSE, CRA/CRR (GSA), phs (dbGaP),
EGAS/EGAD; section-aware (data_availability > methods > back_matter > results); supplementary
tables mined via zipfile + openpyxl/pandas. Map to universe studies via run/sample/experiment
accession → study_accession; a paper mentioning ≥2 universe studies is a contested link.

## Enumeration v3 (learned in the 2026-09 growth phase)
* Taxid corrections: human feces metagenome = **2705415**; human milk metagenome = **1633571** (both earlier ids return 0 runs).
* Slices that found real infant studies the taxon frame missed, in order of yield per study judged:
  1. **Misfiled `library_source=GENOMIC`** on human gut/feces metagenome taxa with strategy WGS/WXS (287 studies → 13 infant cohorts). Treat as shotgun if the record describes community sequencing.
  2. Generic taxon **256318 "metagenome"** (no host_tax_id; ~2,400 studies, 95% environmental/animal → deterministic auto-exclude first, then rubric).
  3. Virome taxa ("human viral metagenome", "viral metagenome") — VLP-enriched DNA shotgun of infant stool (e.g. COPSAC).
  4. OTHER/Targeted-Capture for tax_eq(9606) plus depth-signature adjudication (≥1e8 bases, 100–300 nt, no target_gene).
* Literature snowball (Semantic Scholar refs+cites of linked papers) and GMrepo (host_age ≤3) found nothing outside the fixed enumeration — use them as recall checks, not discovery.
* Non-INSDC: GSA (ngdc.cncb.ac.cn) search + RunInfo export + BioProject pages are open; CRA detail pages sit behind a JS anti-bot challenge. GSA-Human is controlled-access. CNGBdb `db.cngb.org/search/ajax/project/?q=` works but is slow (10–60 s). Both need `request_network_access`.
* Fixed code: scope_constants_v2.py (artifact 35befdd6) / enumerate_universe_v2.py (94d33671); audit in enumeration_audit_v2.csv.

## Frame-free sweep — the recommended PRIMARY enumeration (learned 2026-09-24)
Taxon frames missed 442 human-signal studies (14 infant cohorts, ~10k samples), 237 of them with a BLANK tax_id. Procedure that found them (frame_free_sweep_report.md, enumerate with harvest_lib streaming limit=0, chunked parquet):
1. Index ALL `library_source="METAGENOMIC" AND library_strategy in (WGS, WXS)` runs with fields run_accession, study_accession, tax_id, scientific_name, host_tax_id (~1.46M runs, 36k studies in 2026-09; several minutes).
2. For studies not in the catalog, pull study title/description + sample-level fields (sample_title, host_*, isolation_source, body_site, environmental_medium).
3. Deterministic human-signal rule (host 9606 / human text / gut-stool terms, not dominated by animal-environment terms) → rubric. Ties flagged 'ambiguous' were 523 → after filters 38 → 0 includes, so the rule's exclusions are safe.
Then use the taxon frames (v3) only as a superset check. Also run the sweep on `library_source="GENOMIC"` restricted to human-metagenome taxa (misfiled deposits) — 13 infant cohorts came from that slice.
Non-INSDC status: KoNA is discontinued (→ K-BDS KRA, kbds.re.kr; 871/1,096 projects are imported PRJNA, 0 infant shotgun native); CNGBdb rate-limits to ~1 req/min after ~45 requests (page size fixed at 10) — 6 native CNP projects, 5 infant-titled, cannot join an INSDC-keyed catalog; GSA: list-only annex (see GSA_ANNEX_ASSESSMENT.md). DDBJ mirrors post-2025 GSA deposits as PRJDB with '(PRJCA…)' in the title.

# DATA_LAYOUT.md — where everything lives (Reviewer A finding A12)

One granted root on the owner's machine, three git clones, two non-git directories. The rw host grant covers
`~/catalog/` only (today's grant on `~/Downloads/site` is retired once the site clone moves).

```
~/catalog/
├── microbiome_repo-pipeline/            git clone github.com/OlmLab/microbiome_repo-pipeline       (THIS repo; code only)
│   ├── src/catalog/             enumeration · harvest · triage · extraction · prompts · legacy · apply_findings · make_version · models
│   ├── site_generator/gen/      build_site.py, templates/, static/, check_links.py
│   ├── config/                  models.yaml · inputs.json · site.yaml · budgets.yaml · version.txt
│   ├── skills/                  vendored SKILL.md + kernel.py of the two published skills (sync test)
│   ├── tests/  docs/  .github/  Makefile  bootstrap.py  environment.yml  requirements.lock
│   ├── audit/findings/          findings CSVs (mirrored into the data repo by `make publish-branch`)
│   ├── data/inputs/             (gitignored) inputs materialised by bootstrap.py — package zip, catalog_studies …
│   └── build/                   (gitignored) package/, site/, applied/, resweep_<cycle>/
├── microbiome_repo-data/     git clone github.com/OlmLab/microbiome_repo-data  (tags data-vX.Y.Z)
│   ├── package/                 the data package tables, each ≤ 50 MB (parquet + csv.gz, ≈ 36 MB total), README,
│   │                            DATA_DICTIONARY, VERSION.json, getting_started.ipynb
│   ├── audit/findings/          YYYY-MM-DD_<source>.csv  (A10: findings live in git, not only as artifacts)
│   ├── reports/                 CATALOG_REPORT, EXTRACTION_REPORT, SANDPIPER_REPORT, CYCLE_LOG (small markdown)
│   └── .github/workflows/release.yml   builds data_package_v<semver>.zip + infant_catalog_v<semver>.sqlite (≈ 200 MB)
│                                        and attaches them as Release assets; Zenodo integration mints the DOI
├── microbiome_repo/          git clone github.com/OlmLab/microbiome_repo        (Pages repo, GENERATED ONLY)
│   ├── index.html studies/ cohorts/ samples/ data/ …   (≈ 220 MB, 2,000 files; every file < 100 MB)
│   └── .github/workflows/{verify,deploy-pages}.yml     Pages source = Actions; history stays small (A2)
├── cache/                       NOT git, NOT artifacts.  harvest_cache/ untarred from harvest_cache.tar.gz
│   └── harvest_cache/           http_cache.sqlite + blobs/ (≈ 9.7 GB compressed, ≈ 25 GB on disk) + harvest_cache.sha256
├── external/                    NOT git.  external/sandpiper/<zenodo_record_version>/ raw bulk files + sha256 (one snapshot artifact per version too)
└── data/                        NOT git.  Drop zone bootstrap.py reads before the artifact store
                                 (data_package_v1.zip, catalog_studies.parquet, study_triage_v2.parquet, …)
```

## What goes where (decision rule)

| thing | size | home | why |
|---|---|---|---|
| code, config, docs, tests, workflows | < 5 MB | `microbiome_repo-pipeline` (git) | reviewable, tagged with the release |
| package tables ≤ 50 MB each | ≈ 36 MB total | `microbiome_repo-data` (git, committed) | diffable history per release; the site downloads point at Release assets |
| `data_package_v*.zip`, `infant_catalog_v*.sqlite` (200 MB), full Sandpiper profiles (80–250 MB, provisional) | large | GitHub **Release assets built by Actions** (+ Zenodo DOI) | > 100 MB file cap and history growth; agent cannot upload assets (A1) |
| generated site | 220 MB | `microbiome_repo` via Pages-from-Actions; `release/<semver>` branches + `site-v*` tags | no unbounded `main` history (A2) |
| harvest cache | 9.7 GB | `~/catalog/cache/` + ONE snapshot artifact per release (`harvest_cache.tar.gz`, snapshot destination, older deleted by policy) | resume substrate; a working_data artifact keeps only the latest copy — one bad save destroys it (A4a) |
| Sandpiper bulk snapshots | 3.7 GB per Zenodo version | `~/catalog/external/sandpiper/<version>/` **plus ONE snapshot artifact per Zenodo version** (2.0.0: artifact `8071e8b8-9565-4979-b2aa-87614b3b35d5`, sha256 `4732c4e1b89c2f716f4542add715f4e934139b1e818e8cc814eaceff6411065d`, listed in `config/inputs.json` group `sandpiper`) | never git; the artifact is the durable copy while `~/catalog/external` does not exist (R1-14); re-fetchable from Zenodo record 20419175 |
| per-step evidence trails, LLM raw outputs, superseded/rejected determinations, release bundles | 70 MB / release | **artifacts only** (`release_bundle.tar.gz`) — summarised in `reports/` | provenance without bloating the repos |
| findings CSVs | KB | `audit/findings/` in BOTH the pipeline repo (working copy) and the data repo (published) | the site's "Report an issue" → Issue → CSV loop (B4) |

## Sizes today (v11)
package zip 26 MB · sqlite 200 MB · site 220 MB / 1,998 files · release bundle 69 MB · harvest cache 9.75 GB ·
artifact store 785 artifacts / 10.8 GB (retention policy: keep the latest release bundle + one harvest-cache
snapshot per release; delete intermediate `*_checkpoint_*` parquet older than two releases).

## Rules
* `.gitignore` in every clone: `.DS_Store`, caches, `build/`, `*.sqlite`, `node_modules/`.
* The only `--delete` rsyncs are `build/` ← package and clone working tree ← `build/site` (Makefile). Never
  `rm -rf` inside `~/catalog/` except `build/` (`make clean`).
* One writer per clone at a time: the Release Engineer profile; the Curator writes only under
  `microbiome_repo-pipeline/build/` and `audit/findings/`.

## Release outputs (R2026.1)
`build/package/` carries `sample_determinations_all.parquet`, `releases.csv`, `RELEASE_NOTES_<release_id>.md`, `bitemporal_log.json` next to the tables; `docs/package_changelog/<semver>.md` is the source of the package CHANGELOG entry. Data package zips are named `data_package_v<semver>.zip`; the release id lives in `VERSION.json.release_id`.

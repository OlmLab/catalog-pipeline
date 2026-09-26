#!/usr/bin/env python
"""package_docs.py — regenerate build_counts.json from the tables and bring the package docs up to the release.

    python -m catalog.release.package_docs --package build/package --package-version 1.3.0 --release-id R2026.1 \
        --build-date 2026-09-26 [--changelog-entry docs/package_changelog/1.3.0.md]

* build_counts.json: recomputed from the tables (n_samples, n_studies, n_catalog_scope, n_biosample_units, n_run_units,
  n_runs, n_profiled_samples, n_author_rows, n_determinations_current, package_version, release_id) — the 1.2.2
  package shipped a stale copy (package_version 1.2.1, n_catalog_scope 71,795).
* README.md: heading → "data package v<semver> (<build_date>)" (make_version --check requires it), Files-table rows for
  the new files, a "Release model" section (once).
* DATA_DICTIONARY.md: the three release columns appended to every fact table's section / complete column reference,
  a section for sample_determinations_all.parquet and releases.csv, with the reconstruction caveat (once).
* CHANGELOG.md: the entry file is prepended when its first heading is not yet present.
Deterministic and idempotent (re-running on an updated package changes nothing).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

import pandas as pd
import pyarrow.parquet as pq
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
CONFIG_DIR = os.environ.get("CATALOG_CONFIG_DIR", os.path.join(REPO, "config"))
COLS = ("release_added", "release_retired", "package_added")
COL_DOC = {
    "release_added": "release in which this row first became visible (`R<YYYY>.<n>` or a pre-numbered package semver `1.0.0`–`1.2.2`); pre-1.3.0 values are reconstructed — see DATA_DICTIONARY 'Release columns'",
    "release_retired": "release that replaced/removed the row; null (empty in CSV) = current row",
    "package_added": "semver of the data package in which the row first appeared",
}


def _rows(path: str) -> int:
    if path.endswith(".parquet"):
        return pq.ParquetFile(path).metadata.num_rows
    with open(path, "rb") as f:
        return max(sum(1 for _ in f) - 1, 0)


def build_counts(pkg: str, package_version: str, release_id: str) -> dict:
    smw = pd.read_parquet(os.path.join(pkg, "sample_metadata_wide.parquet"), columns=["sample_key", "catalog_scope", "sample_unit", "age_scope", "body_site_class"])
    c = dict(package_version=package_version, release_id=release_id,
             n_samples=int(len(smw)), n_catalog_scope=int(smw["catalog_scope"].fillna(False).astype(bool).sum()),
             n_biosample_units=int((smw["sample_unit"] == "biosample").sum()), n_run_units=int((smw["sample_unit"] == "run").sum()),
             n_age_scope_infant=int(smw["age_scope"].isin(["infant_evidenced", "study_all_infant"]).sum()),
             n_body_site_excluded=int((smw["body_site_class"] == "excluded").sum()),
             n_studies=_rows(os.path.join(pkg, "study_metadata_wide.parquet")), n_runs=_rows(os.path.join(pkg, "runs.parquet")),
             n_determinations_current=_rows(os.path.join(pkg, "sample_determinations.parquet")))
    for key, fn in (("n_profiled_samples", "sandpiper_sample_summary.parquet"), ("n_author_rows", "authors.parquet"),
                    ("n_parent_biosamples", "parent_biosamples.parquet"), ("n_universe_studies", "universe_studies_all.parquet"),
                    ("n_determinations_all", "sample_determinations_all.parquet"), ("n_value_history", "value_history.parquet")):
        p = os.path.join(pkg, fn)
        if os.path.exists(p):
            c[key] = _rows(p)
    all_p = os.path.join(pkg, "sample_determinations_all.parquet")
    if os.path.exists(all_p):
        rr = pd.read_parquet(all_p, columns=["release_retired"])["release_retired"]
        c["n_determinations_retired"] = int(rr.notna().sum())
    c["n_wide_cols"] = len(pq.ParquetFile(os.path.join(pkg, "sample_metadata_wide.parquet")).schema_arrow.names)
    c["n_study_cols"] = len(pq.ParquetFile(os.path.join(pkg, "study_metadata_wide.parquet")).schema_arrow.names)
    return c


def update_readme(pkg: str, package_version: str, release_id: str, build_date: str, counts: dict) -> None:
    p = os.path.join(pkg, "README.md")
    s = open(p, encoding="utf-8").read()
    s, n = re.subn(r"data package v\d+(?:\.\d+)* \(\d{4}-\d{2}-\d{2}\)", f"data package v{package_version} ({build_date})", s, count=1)
    assert n == 1, "README heading 'data package vX.Y.Z (date)' not found"
    marker = "## Release model"
    if marker not in s:
        rows = [f"| `sample_determinations_all.parquet` | {counts.get('n_determinations_all', ''):,} | Current **and retired** determinations: `sample_determinations` columns + `release_added`, `release_retired` (null = current), `package_added`, `retired_reason`, `retired_change_stage` — the per-field value timeline — {release_id} |",
                f"| `releases.csv` | {counts.get('n_releases', ''):,} | Release registry: one row per release id (package version, date, tags, DOI, headline counts, notes file) — {release_id} |",
                f"| `RELEASE_NOTES_{release_id}.md` | | Generated diff report vs the previous package (studies/samples, coverage, verdict flips, findings, Sandpiper, gold, schema) — {release_id} |"]
        anchor = "| `DATA_DICTIONARY.md` | | Every column, every vocabulary |"
        assert anchor in s, "README Files table anchor row not found"
        s = s.replace(anchor, "\n".join(rows) + "\n" + anchor, 1)
        section = f"""
## Release model ({release_id}, package {package_version})
This is the first **numbered catalog release** (`R<YYYY>.<n>`; `VERSION.json.release_id`). Every fact table
(`sample_determinations`, `universe_studies_all`, `study_metadata_wide`, `cohorts`, `study_paper_links`, `sandpiper_*`)
carries three trailing columns `release_added`, `release_retired` (null = current) and `package_added`; `sample_metadata_wide`
is derived and has none. `sample_determinations_all.parquet` adds the retired determinations ({counts.get('n_determinations_retired', 0):,} rows,
reconstructed from `value_history`) so a per-field value timeline is one `ORDER BY release_added` query; `releases.csv` is the
registry of every release. **Caveat:** packages before 1.3.0 had no release columns, so `release_added` for pre-existing rows is
reconstructed from `value_history.change_stage` / `src_track` and is exact only for rows those stages touched (adult-age
recommits, run-level rows, retired values); every other pre-1.3.0 row is labelled `1.0.0` by assumption. Full rules:
`DATA_DICTIONARY.md` 'Release columns' and the pipeline's `docs/RELEASES.md`.
"""
        s = s.replace("\n## How to read a value", section + "\n## How to read a value", 1)
    open(p, "w", encoding="utf-8").write(s)


def update_dictionary(pkg: str, package_version: str, release_id: str, cfg: dict, counts: dict) -> None:
    p = os.path.join(pkg, "DATA_DICTIONARY.md")
    s = open(p, encoding="utf-8").read()
    if "## Release columns" in s:
        return
    fact_files = [t["file"] for t in cfg["fact_tables"]] + [t.get("csv_twin") for t in cfg["fact_tables"] if t.get("csv_twin")]
    # 1. sample_determinations section (two-column table) — append rows before "## Routes"
    det_rows = "\n".join(f"| `{c}` | {COL_DOC[c]} |" for c in COLS)
    s = s.replace("| `src_track` | pipeline pass that produced the row |\n", f"| `src_track` | pipeline pass that produced the row |\n{det_rows}\n", 1)
    # 2. complete column reference for study_metadata_wide (3-column table; the build fails on an undocumented column)
    m = re.search(r"### study_metadata_wide\.parquet \((\d+) columns\)", s)
    if m:
        n = int(m.group(1))
        s = s.replace(m.group(0), f"### study_metadata_wide.parquet ({n + 3} columns)", 1)
        tail = "| `shared_biosample_note` | object | human-readable note for the five studies sharing BioSamples (F6) |"
        assert tail in s
        s = s.replace(tail, tail + "\n" + "\n".join(f"| `{c}` | string | {COL_DOC[c]} |" for c in COLS), 1)
    section = f"""
## Release columns ({release_id}, package {package_version})
Fact tables — {', '.join(f'`{f}`' for f in fact_files)} — end with three columns:

| column | dtype | meaning |
|---|---|---|
| `release_added` | string | {COL_DOC['release_added']} |
| `release_retired` | string \\| null | {COL_DOC['release_retired']} |
| `package_added` | string | {COL_DOC['package_added']} |

Release ids are `R<YYYY>.<n>` (first: `{release_id}` = package {package_version}) or, for states published before numbering, the package
semver `1.0.0` (first public package, 2026-09-25), `1.1.0` (release v11), `1.2.0`, `1.2.1`, `1.2.2`. "Current" = `release_retired IS NULL`;
in the shipped fact tables every row is current. `sample_metadata_wide` is derived from `sample_determinations` and carries no release columns.

**Reconstruction caveat.** Packages before 1.3.0 carried no release columns, so `release_added` of pre-existing rows was reconstructed:
newest `value_history.change_stage` touching the (sample_key, field_name) or `sample_determinations.src_track`, mapped to the package the
CHANGELOG records for that stage (`sample_unit_fix` → 1.1.0, `auditor_review:B2`/`B9` → 1.2.0, `auditor_review:R3-3` → 1.2.1,
`owner_decision` → 1.2.2). Exact for rows those stages touched ({counts.get('n_release_added_reconstructed', '')} current determinations:
`src_track = sample_unit_fix` → 1.1.0, `src_track = adult_scope_fix` → 1.2.0); every other pre-1.3.0 row is labelled `1.0.0` by assumption
(the first package is not archived as a table, so this cannot be verified row by row). `package_added` equals `release_added` for all
pre-1.3.0 rows. Study verdict rows are all `1.0.0` (no verdict change is dated after the first package); Sandpiper rows are `1.2.0`
(when Sandpiper landed; the v1.2.1 recomputation of existing rows is recorded in the CHANGELOG, not as retire+add).

## sample_determinations_all.parquet ({release_id})
`sample_determinations` columns + the three release columns + `retired_reason` (string|null; `value_history.reason`) +
`retired_change_stage` (string|null; `value_history.change_stage`). Rows: every current determination ({counts.get('n_determinations_current', 0):,},
`release_retired` null) ∪ every **retired published value** ({counts.get('n_determinations_retired', 0):,}) reconstructed from `value_history`
rows whose `status` ∈ {{`superseded`, `moved_to_parent_biosamples`, `recommitted_out_of_scope_host`, `recommitted_out_of_scope_isolate`}}
(`release_retired` = the package of their `change_stage`). value_history rows with status `rejected`, `dropped`, `not_committed_duplicate`,
`recommitted_out_of_scope_adult` (the pre-history of a row that IS current) or `auditor_finding_applied` were never published and are not
rows here. Exactly one current row per (`sample_key`, `field_name`); retired rows may repeat a key. `sample_determinations_superseded.parquet`
(223 rows) is the same set as the `superseded` rows of stages `sample_unit_fix` (75) and `auditor_review:B9` (148) and is kept for the v1.1 layout.

## releases.csv ({release_id})
One row per release id, oldest first: `release_id`, `package_version`, `release_date`, `data_tag`, `site_tag`, `doi` (empty until Zenodo
mints one), `n_studies_included`, `n_samples`, `n_catalog_scope`, `n_determinations_current`, `sandpiper_version`, `notes_file`. Historical
rows carry only the counts the CHANGELOGs state (empty otherwise — never invented).
"""
    s = s.replace("\n## Sandpiper columns (added v1.2.0)", section + "\n## Sandpiper columns (added v1.2.0)", 1)
    open(p, "w", encoding="utf-8").write(s)


def prepend_changelog(pkg: str, entry_path: str | None) -> bool:
    if not entry_path or not os.path.exists(entry_path):
        return False
    p = os.path.join(pkg, "CHANGELOG.md")
    entry = open(entry_path, encoding="utf-8").read().rstrip() + "\n\n"
    s = open(p, encoding="utf-8").read()
    head = entry.splitlines()[0].strip()
    if head in s:
        return False
    open(p, "w", encoding="utf-8").write(entry + s)
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--package", required=True)
    ap.add_argument("--package-version", required=True)
    ap.add_argument("--release-id", required=True)
    ap.add_argument("--build-date", required=True)
    ap.add_argument("--changelog-entry", default=None)
    ap.add_argument("--config", default=None)
    a = ap.parse_args(argv)
    cfg = yaml.safe_load(open(a.config or os.path.join(CONFIG_DIR, "releases.yaml"), encoding="utf-8"))
    counts = build_counts(a.package, a.package_version, a.release_id)
    reg = os.path.join(a.package, cfg["files"]["registry"])
    counts["n_releases"] = _rows(reg) if os.path.exists(reg) else 0
    sd_p = os.path.join(a.package, "sample_determinations.parquet")
    ra = pd.read_parquet(sd_p, columns=["release_added"])["release_added"] if "release_added" in pq.ParquetFile(sd_p).schema_arrow.names else None
    counts["n_release_added_reconstructed"] = int((ra != cfg["fact_tables"][0]["default_release_added"]).sum()) if ra is not None else 0
    counts["release_added_counts"] = ra.value_counts().sort_index().to_dict() if ra is not None else {}
    json.dump(counts, open(os.path.join(a.package, "build_counts.json"), "w"), indent=1, sort_keys=True)
    update_readme(a.package, a.package_version, a.release_id, a.build_date, counts)
    update_dictionary(a.package, a.package_version, a.release_id, cfg, counts)
    changed = prepend_changelog(a.package, a.changelog_entry)
    print(json.dumps({k: counts[k] for k in ("package_version", "release_id", "n_samples", "n_studies", "n_catalog_scope", "n_determinations_current")} | {"changelog_prepended": changed}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

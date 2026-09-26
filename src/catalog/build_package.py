#!/usr/bin/env python
"""build_package.py (generalised from build_package_v120.py, R1-03) — assemble a data package from the previous package + Sandpiper + authors tables.

--package-version defaults to config/version.txt; --zip writes the deterministic zip via catalog.make_version.build_zip (R1-11).

Deterministic, no LLM. Every number written into README/CHANGELOG is computed here from the tables.

    python -m catalog.build_package --v12 DIR --sandpiper DIR --authors DIR --out DIR --build-date 2026-09-26

Adds to sample_metadata_wide: sp_* columns (join sandpiper_sample_summary on sample_key; sp_profiled False when
absent), <field>__scope for the 16 coverage fields (from sample_determinations.scope).
Adds to study_metadata_wide: sp_n_samples_profiled, sp_frac_samples_profiled, sp_frac_runs_profiled,
sp_frac_runs_flagged (non-metagenome strict, non-human/microbe named), sp_frac_low_complexity_profiled,
sp_median_spf, sp_median_known_species_fraction, first_author, n_authors, organisations.
Copies the on-site Sandpiper tables and the authors tables; rewrites *.csv.gz with gzip mtime=0; then VERSION.json.
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import os
import re
import shutil
import sys
import zipfile

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from catalog import make_version  # noqa: E402

COV_FIELDS = ['age_at_collection_days', 'delivery_mode', 'feeding_mode', 'preterm_status', 'antibiotic_exposure',
              'gestational_age_weeks', 'birth_weight_grams', 'probiotic_exposure', 'maternal_antibiotics',
              'hmo_supplementation', 'nec_status', 'country', 'health_condition', 'multiple_birth',
              'sibling_in_study', 'geo_subregion']
SP_SAMPLE_COLS = ['sp_profiled', 'sandpiper_url', 'sp_n_runs_total', 'sp_n_runs_profiled', 'sp_partial', 'sp_spf',
                  'sp_known_species_fraction', 'sp_root_coverage', 'sp_low_depth', 'sp_top_genus', 'sp_top_genus_ra',
                  'sp_ra_g_Bifidobacterium', 'sp_ra_f_Bacteroidaceae', 'sp_ra_g_Bacteroides', 'sp_ra_g_Phocaeicola',
                  'sp_ra_enterobacterales_core', 'sp_ra_g_Escherichia', 'sp_ra_g_Klebsiella', 'sp_ra_f_Lachnospiraceae',
                  'sp_ra_f_Lactobacillaceae', 'sp_ra_g_Streptococcus', 'sp_ra_g_Staphylococcus', 'sp_ra_g_Enterococcus',
                  'sp_ra_g_Veillonella', 'sp_ra_g_Clostridioides', 'sp_ra_unassigned_genus', 'sp_shannon_genus',
                  'sp_n_genera_ge1pct', 'sp_flag_low_complexity', 'sp_flag_non_metagenome', 'sp_flag_synthetic',
                  'sp_flag_rna', 'sp_flag_readfraction_warning', 'sp_run_concordance_bc', 'sp_runs_discordant',
                  'taxonomy_db', 'taxonomy_version', 'sandpiper_version']
SANDPIPER_ONSITE = ['sandpiper_sample_summary.parquet', 'sandpiper_top_genera.parquet', 'sandpiper_study_panels.parquet',
                    'sandpiper_run_qc.parquet', 'sandpiper_study_coverage.csv', 'sandpiper_study_qc_flags.csv',
                    'sandpiper_flag_definitions.json', 'SANDPIPER_REPORT.md']
AUTHORS_FILES = ['authors.parquet', 'study_authors_summary.csv', 'authors_index.json', 'AUTHORS_REPORT.md']


def write_csv_gz(df: pd.DataFrame, path: str):
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    with open(path, 'wb') as fh:
        with gzip.GzipFile(filename='', mode='wb', fileobj=fh, mtime=0) as gz:
            gz.write(buf.getvalue().encode('utf-8'))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--v12', required=True, help='unzipped data_package_v1.2 directory')
    ap.add_argument('--sandpiper', required=True, help='dir holding the sandpiper_* tables + SANDPIPER_REPORT.md')
    ap.add_argument('--authors', required=True, help='dir holding authors.parquet, study_authors_summary.csv, authors_index.json, AUTHORS_REPORT.md')
    ap.add_argument('--extra-docs', default=None, help='dir with DATA_MODEL_FIX_REPORT.md etc. to copy if missing')
    ap.add_argument('--out', required=True)
    ap.add_argument('--package-version', default=None)
    ap.add_argument('--build-date', required=True, help='package release date YYYY-MM-DD (the site footer uses it)')
    ap.add_argument('--zip', default=None, help='also write a deterministic zip here')
    a = ap.parse_args(argv)
    version = a.package_version or make_version.read_version()
    out = a.out
    if os.path.exists(out):
        shutil.rmtree(out)
    os.makedirs(out)
    for name in sorted(os.listdir(a.v12)):
        p = os.path.join(a.v12, name)
        if os.path.isfile(p) and name != 'VERSION.json':
            shutil.copy(p, os.path.join(out, name))

    # ---- sample table + Sandpiper + scope ----
    sw = pd.read_parquet(os.path.join(a.v12, 'sample_metadata_wide.parquet'))
    n0 = len(sw)
    assert sw.sample_key.is_unique
    assert (sw.sample_unit != 'biosample_pooled').all(), 'parent rows must not be in the sample table (B2)'
    sp = pd.read_parquet(os.path.join(a.sandpiper, 'sandpiper_sample_summary.parquet'))
    assert sp.sample_key.is_unique
    sp = sp[['sample_key'] + [c for c in SP_SAMPLE_COLS if c in sp.columns]]
    sw = sw.merge(sp, on='sample_key', how='left')
    assert len(sw) == n0
    sw['sp_profiled'] = sw['sp_profiled'].fillna(False).astype(bool)
    for c in ['sp_partial', 'sp_low_depth', 'sp_flag_low_complexity', 'sp_flag_non_metagenome', 'sp_flag_synthetic',
              'sp_flag_rna', 'sp_flag_readfraction_warning', 'sp_runs_discordant']:
        if c in sw.columns:
            sw[c] = sw[c].where(sw.sp_profiled, other=pd.NA).astype('boolean')
    # sample-level Sandpiper URL for unprofiled run-unit rows: link the run itself (Sandpiper resolves by run)
    sd = pd.read_parquet(os.path.join(a.v12, 'sample_determinations.parquet'), columns=['sample_key', 'field_name', 'scope'])
    sd = sd[sd.field_name.isin(COV_FIELDS)].drop_duplicates(['sample_key', 'field_name'])
    scope = sd.pivot(index='sample_key', columns='field_name', values='scope')
    scope.columns = [f'{c}__scope' for c in scope.columns]
    sw = sw.merge(scope, left_on='sample_key', right_index=True, how='left')
    for f in COV_FIELDS:
        col = f'{f}__scope'
        if col not in sw.columns:
            sw[col] = pd.NA
        sw[col] = sw[col].where(sw[f].notna(), other=pd.NA)
    sw = sw.sort_values('sample_key').reset_index(drop=True)
    sw.to_parquet(os.path.join(out, 'sample_metadata_wide.parquet'), index=False, compression='zstd')
    write_csv_gz(sw, os.path.join(out, 'sample_metadata_wide.csv.gz'))

    # ---- study table ----
    st = pd.read_parquet(os.path.join(a.v12, 'study_metadata_wide.parquet'))
    cov = pd.read_csv(os.path.join(a.sandpiper, 'sandpiper_study_coverage.csv'))
    qc = pd.read_csv(os.path.join(a.sandpiper, 'sandpiper_study_qc_flags.csv'))
    g = sw.groupby('study_accession')
    per = pd.DataFrame({'sp_n_samples_profiled': g.sp_profiled.sum().astype(int),
                        'sp_frac_samples_profiled': g.sp_profiled.mean(),
                        'sp_median_bifidobacterium_ra': g.sp_ra_g_Bifidobacterium.median(),
                        'sp_median_shannon_genus': g.sp_shannon_genus.median()}).reset_index()
    st = st.merge(per, on='study_accession', how='left')
    st = st.merge(cov[['study_accession', 'n_runs_profiled', 'frac_runs_profiled', 'coverage_class']]
                  .rename(columns={'n_runs_profiled': 'sp_n_runs_profiled', 'frac_runs_profiled': 'sp_frac_runs_profiled',
                                   'coverage_class': 'sp_coverage_class'}), on='study_accession', how='left')
    qc['sp_frac_runs_flagged'] = qc[['frac_named_nonhuman_host', 'frac_named_microbe', 'frac_synthetic', 'frac_rna_strict']].sum(axis=1).clip(upper=1.0)
    st = st.merge(qc[['study_accession', 'sp_frac_runs_flagged', 'frac_low_complexity_profiled', 'frac_low_depth_profiled',
                      'median_spf', 'median_known_species_fraction', 'auditor_attention', 'auditor_reason']]
                  .rename(columns={'frac_low_complexity_profiled': 'sp_frac_low_complexity_profiled',
                                   'frac_low_depth_profiled': 'sp_frac_low_depth_profiled', 'median_spf': 'sp_median_spf',
                                   'median_known_species_fraction': 'sp_median_known_species_fraction',
                                   'auditor_attention': 'sp_auditor_attention', 'auditor_reason': 'sp_auditor_reason'}),
                  on='study_accession', how='left')
    sas = pd.read_csv(os.path.join(a.authors, 'study_authors_summary.csv'))
    st = st.merge(sas[['study_accession', 'first_author', 'last_author', 'n_authors', 'n_papers', 'organisations']]
                  .rename(columns={'n_papers': 'n_author_papers'}), on='study_accession', how='left')
    st['n_authors'] = st['n_authors'].fillna(0).astype(int)
    st = st.sort_values('study_accession').reset_index(drop=True)
    st.to_parquet(os.path.join(out, 'study_metadata_wide.parquet'), index=False)
    st.to_csv(os.path.join(out, 'study_metadata_wide.csv'), index=False)

    # ---- copy Sandpiper + authors tables ----
    for name in SANDPIPER_ONSITE:
        shutil.copy(os.path.join(a.sandpiper, name), os.path.join(out, name))
    for name in AUTHORS_FILES:
        shutil.copy(os.path.join(a.authors, name), os.path.join(out, name))
    if a.extra_docs:
        for name in sorted(os.listdir(a.extra_docs)):
            if name.endswith('.md') and not os.path.exists(os.path.join(out, name)):
                shutil.copy(os.path.join(a.extra_docs, name), os.path.join(out, name))
    # every other csv.gz deterministic too
    for name in sorted(os.listdir(out)):
        if name.endswith('.csv.gz') and name != 'sample_metadata_wide.csv.gz':
            p = os.path.join(out, name)
            raw = gzip.open(p, 'rb').read()
            with open(p, 'wb') as fh, gzip.GzipFile(filename='', mode='wb', fileobj=fh, mtime=0) as gz:
                gz.write(raw)

    # ---- counts for the docs ----
    n_prof = int(sw.sp_profiled.sum())
    au = pd.read_parquet(os.path.join(a.authors, 'authors.parquet'))
    counts = dict(n_samples=int(len(sw)), n_studies=int(len(st)), n_profiled_samples=n_prof,
                  frac_profiled=round(n_prof / len(sw), 4),
                  n_studies_with_profiles=int((st.sp_n_samples_profiled.fillna(0) > 0).sum()),
                  n_runs_profiled=int(cov.n_runs_profiled.sum()), n_runs=int(cov.n_runs.sum()),
                  n_author_rows=int(len(au)), n_distinct_authors=int(au.author_key.nunique()),
                  n_studies_with_author=int(sas.has_any_author.sum()),
                  n_included_without_author=int(((sas.catalog_status == 'included') & (~sas.has_any_author.astype(bool))).sum()),
                  n_sp_cols=len([c for c in sw.columns if c.startswith('sp_') or c in ('sandpiper_url', 'taxonomy_db', 'taxonomy_version', 'sandpiper_version')]),
                  n_scope_cols=len(COV_FIELDS), n_wide_cols=int(sw.shape[1]))

    # ---- README / DATA_DICTIONARY / CHANGELOG ----
    readme_p = os.path.join(out, 'README.md')
    readme = open(readme_p, encoding='utf-8').read()
    readme = re.sub(r'data package v\d+(?:\.\d+)*( \([^)]*\))?', f'data package v{version} ({a.build_date})', readme, count=1)
    readme += f"""

## Added in v{version}: Sandpiper community profiles and author index
* `sample_metadata_wide` carries {counts['n_sp_cols']} Sandpiper columns (`sp_*`, `sandpiper_url`, `taxonomy_db`, `taxonomy_version`, `sandpiper_version`): {counts['n_profiled_samples']:,} of {counts['n_samples']:,} samples ({100*counts['frac_profiled']:.1f}%) in {counts['n_studies_with_profiles']} studies have a SingleM profile (Sandpiper 2.0.0, GTDB R232; {counts['n_runs_profiled']:,} of {counts['n_runs']:,} runs). Relative abundances (`*_ra`) are fractions of prokaryotic coverage — see `SANDPIPER_REPORT.md` §3 and the DATA_DICTIONARY. Every profiled sample links to `https://sandpiper.qut.edu.au/run/<run>`.
* `<field>__scope` (sample / subject / group / biosample) for the 16 coverage fields, so slice exports carry the scope of R3/R4 group statements.
* `study_metadata_wide` adds `sp_n_samples_profiled`, `sp_frac_samples_profiled`, `sp_n_runs_profiled`, `sp_frac_runs_profiled`, `sp_coverage_class`, `sp_frac_runs_flagged` (runs whose organism/library labels fire Sandpiper's non-human-host / named-microbe / synthetic / RNA rules), `sp_frac_low_complexity_profiled`, `sp_frac_low_depth_profiled`, `sp_median_spf`, `sp_median_known_species_fraction`, `sp_median_bifidobacterium_ra`, `sp_median_shannon_genus`, `sp_auditor_attention`, `sp_auditor_reason`, and the author columns `first_author`, `last_author`, `n_authors`, `n_author_papers`, `organisations`.
* On-site Sandpiper tables: `sandpiper_sample_summary.parquet`, `sandpiper_top_genera.parquet` (top-15 genera + unassigned bin per sample), `sandpiper_study_panels.parquet` (per-study mean top phyla/genera), `sandpiper_run_qc.parquet` (all runs, QC flags, miss reasons), `sandpiper_study_coverage.csv`, `sandpiper_study_qc_flags.csv`, `sandpiper_flag_definitions.json`. The full run × taxon profiles (`sandpiper_profiles.parquet`, ~100 MB) are a Release asset, not in this package.
* Author index: `authors.parquet` ({counts['n_author_rows']:,} study × author rows, {counts['n_distinct_authors']:,} distinct author keys), `study_authors_summary.csv` (first/last author, organisations for all screened studies), `authors_index.json` (search index used by the website). Names are string-matched from Europe PMC author strings and NCBI BioProject records; {counts['n_included_without_author']} included studies have no author on record (see `AUTHORS_REPORT.md`).
* `VERSION.json`: package version, release tag, build date and sha256 + row count of every table.
"""
    open(readme_p, 'w', encoding='utf-8').write(readme)

    dd_p = os.path.join(out, 'DATA_DICTIONARY.md')
    dd = open(dd_p, encoding='utf-8').read()
    dd += """

## Sandpiper columns (added v1.2.0)
Source: SingleM community profiles from Sandpiper 2.0.0 (Woodcroft et al. 2025, *Nat Biotechnol*; Zenodo record 20419175, CC-BY), taxonomy GTDB R232. Profiles are keyed by run; for a catalog sample with several profiled runs the filled coverage per taxon is **summed across runs and then normalised** (never averaged). Every `*_ra` column is a **fraction of prokaryotic (Bacteria + Archaea) coverage** — approximately a cell proportion, not a read fraction; not comparable with MetaPhlAn or 16S numbers.

| column | meaning |
|---|---|
| `sp_profiled` | True when at least one run of the sample has a Sandpiper profile |
| `sandpiper_url` | `https://sandpiper.qut.edu.au/run/<first profiled run>` |
| `sp_n_runs_total`, `sp_n_runs_profiled`, `sp_partial` | run counts; `sp_partial` = some runs unprofiled |
| `sp_spf` | prokaryotic read fraction (%), metagenome-size-weighted over runs |
| `sp_known_species_fraction` | % of prokaryotic coverage assigned to a named GTDB species |
| `sp_root_coverage` | summed root coverage (× genome equivalents); `sp_low_depth` = root < 2× (bars hidden) |
| `sp_top_genus`, `sp_top_genus_ra` | most abundant genus-level bin (may be `unassigned_at_genus`) |
| `sp_ra_g_Bifidobacterium` | GTDB `g__Bifidobacterium` (stable genus) |
| `sp_ra_f_Bacteroidaceae`, `sp_ra_g_Bacteroides`, `sp_ra_g_Phocaeicola` | GTDB moved *B. vulgatus/dorei/plebeius/coprocola* to *Phocaeicola*; the family ≈ NCBI-sense *Bacteroides* |
| `sp_ra_enterobacterales_core` | Σ of six GTDB genera: Escherichia, Klebsiella, Enterobacter, Citrobacter, Salmonella, Serratia (GTDB `f__Enterobacteriaceae` is broader than NCBI's, so the family is not used) |
| `sp_ra_g_Escherichia`, `sp_ra_g_Klebsiella`, `sp_ra_f_Lachnospiraceae`, `sp_ra_f_Lactobacillaceae` (GTDB splits *Lactobacillus*), `sp_ra_g_Streptococcus`, `sp_ra_g_Staphylococcus`, `sp_ra_g_Enterococcus`, `sp_ra_g_Veillonella`, `sp_ra_g_Clostridioides` (*C. difficile*) | indicator taxa |
| `sp_ra_unassigned_genus` | coverage not resolved to a genus (novel fraction; never renormalised away) |
| `sp_shannon_genus`, `sp_n_genera_ge1pct` | Shannon (ln) over genus bins incl. the unassigned bin; named genera ≥ 1 % |
| `sp_flag_low_complexity` | Sandpiper low-complexity rule — expected for Bifidobacterium-/Enterobacterales-dominated neonatal stool; display only, never triage |
| `sp_flag_non_metagenome`, `sp_flag_synthetic`, `sp_flag_rna`, `sp_flag_readfraction_warning` | Sandpiper's published rules reproduced on the run's organism/library labels (`sandpiper_flag_definitions.json`) |
| `sp_run_concordance_bc`, `sp_runs_discordant` | max pairwise genus-level Bray–Curtis between the sample's runs; discordant = BC > 0.5 (human-review hint, not a verdict) |
| `taxonomy_db`, `taxonomy_version`, `sandpiper_version` | GTDB / R232 / 2.0.0 on every profiled row |

`<field>__scope` (16 coverage fields): scope of the winning determination — `sample`, `subject`, `biosample` (propagated from a parent BioSample) or `group` (R3/R4 statement applied to a defined group). Apply the README reading rule to `group`-scope values.

Study columns `sp_*`: fractions over the study's samples/runs as named; `sp_frac_runs_flagged` sums the non-human-host, named-microbe, synthetic and RNA rule fractions (the routine "Homo sapiens" host label is *not* counted). `sp_auditor_attention`/`sp_auditor_reason`: the Sandpiper track's hint that a study deserves a human look (never a verdict).

## Author columns (added v1.2.0)
`authors.parquet`: one row per study × author × paper (`author_display`, `author_surname`, `author_initials`, `is_group`, `source` ∈ linked_paper / bioproject_publication / ena_study_xref, `pmid`, `doi`, `position`, `n_authors`, `is_first`, `is_last`, `paper_relation`, `catalog_status`). `study_authors_summary.csv`: per screened study `first_author`, `last_author`, `n_authors`, `n_papers`, `organisations` (ENA centre / broker and NCBI BioProject owner names, `;`-joined). Names are string-matched from Europe PMC `authorString`; the same person may appear under several initial variants and no disambiguation was attempted.
"""
    open(dd_p, 'w', encoding='utf-8').write(dd)

    cl_p = os.path.join(out, 'CHANGELOG.md')
    cl = open(cl_p, encoding='utf-8').read()
    entry = f"""## v{version} — {a.build_date} (release v12) — Sandpiper profiles, author index, versioning
Deterministic changes only; no LLM calls.
* **Sandpiper (A6, B5, B6, B7).** {counts['n_profiled_samples']:,} / {counts['n_samples']:,} samples profiled ({counts['n_runs_profiled']:,} / {counts['n_runs']:,} runs); {counts['n_sp_cols']} `sp_*` columns on the sample table, 16 `sp_*` columns on the study table; seven on-site Sandpiper tables; full profiles off-site.
* **Scope (B13).** `<field>__scope` for the {counts['n_scope_cols']} coverage fields.
* **Authors.** `authors.parquet` ({counts['n_author_rows']:,} rows), `study_authors_summary.csv`, `authors_index.json`; `first_author`, `n_authors`, `organisations` on the study table.
* **Versioning (A7, B11).** `VERSION.json` with per-table sha256 and row counts; README heading carries the semver; all `*.csv.gz` written with gzip mtime 0 so rebuilds are byte-identical.
* Wide table: {counts['n_wide_cols']} columns.

"""
    cl = cl.replace('# CHANGELOG\n\n', '# CHANGELOG\n\n' + entry, 1)
    open(cl_p, 'w', encoding='utf-8').write(cl)

    # ---- VERSION.json ----
    v = make_version.build(out, version, a.build_date)
    json.dump(v, open(os.path.join(out, 'VERSION.json'), 'w'), indent=1, sort_keys=True)
    probs = make_version.check(out, version)
    if probs:
        raise SystemExit('make_version --check failed: ' + '; '.join(probs))
    json.dump(counts, open(os.path.join(out, 'build_counts.json'), 'w'), indent=1, sort_keys=True)

    if a.zip:
        # R1-03/R1-11: FLAT layout (files at the zip root, no nested package_vX/ dir) so `make unpack` and the site
        # downloads agree; deterministic bytes + .sha256 + sidecar VERSION.json via make_version.build_zip.
        info = make_version.build_zip(out, a.zip, a.build_date)
        make_version.write_sidecar(out, a.zip, info)
        counts['package_zip_sha256'] = info['sha256']
    print(json.dumps(counts))
    return 0


if __name__ == '__main__':
    sys.exit(main())

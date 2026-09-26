#!/usr/bin/env python
"""Build a MOCK 1.3.0 package from an unpacked 1.2.2 package by appending the frozen release columns
(config/releases.yaml) with PLACEHOLDER seeding. Used by the Site track to develop and test the history views
before the Data track's real `src/catalog/release/` output exists. Nothing here is a curated value; the seeding
rules are documented in SITE_HISTORY_REPORT.md and are deterministic.

Usage: python make_mock_release_package.py --src data/inputs/data_package --out build/mock_package_1.3.0 [--config config/releases.yaml]

Seeding (placeholder, NOT the Data track's rules):
  * every fact row: release_added = '1.0.0', release_retired = null, package_added = release_added
  * current sample_determinations rows whose (sample_key, field_name) has a value_history row with
    change_stage owner_decision -> release_added '1.2.2'; auditor_review:* -> '1.2.1'
  * sandpiper_* rows -> '1.2.0' (Sandpiper joined the package in v1.2.0 per CHANGELOG)
  * universe verdict rows: studies with a human_review stage in study_verdict_history -> '1.1.0'
  * sample_determinations_all = current rows UNION value_history rows as retired rows:
    release_retired '1.2.2' (owner_decision) / '1.2.1' (auditor_review:*) / '1.0.0' otherwise,
    retired_reason = value_history.reason, retired_change_stage = value_history.change_stage.
    sample_determinations_superseded.parquet is a strict subset of value_history (checked) so it adds no rows.
"""
import argparse, hashlib, json, sys
from pathlib import Path
import pandas as pd
import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--config', default=str(REPO / 'config' / 'releases.yaml'))
    ap.add_argument('--release-id', default='R2026.1')
    ap.add_argument('--package-version', default='1.3.0')
    ap.add_argument('--release-date', default='2026-09-26')
    a = ap.parse_args()
    src, out = Path(a.src), Path(a.out)
    spec = yaml.safe_load(open(a.config))
    C = spec['columns']
    RA, RR, PA = C['release_added'], C['release_retired'], C['package_added']
    out.mkdir(parents=True, exist_ok=True)
    for f in sorted(src.iterdir()):
        if f.is_file():
            (out / f.name).write_bytes(f.read_bytes())

    vh = pd.read_parquet(src / 'value_history.parquet')
    sup = pd.read_parquet(src / 'sample_determinations_superseded.parquet')
    k = ['sample_key', 'field_name', 'value_normalized']
    assert sup.merge(vh[k].drop_duplicates(), on=k, how='left', indicator=True)._merge.eq('both').all(), 'superseded table must be a subset of value_history'

    def stage_release(cs):
        if cs == 'owner_decision':
            return '1.2.2'
        if isinstance(cs, str) and cs.startswith('auditor_review'):
            return '1.2.1'
        return '1.0.0'
    vh_rel = vh.assign(_rel=vh.change_stage.map(stage_release))
    order = {r: i for i, r in enumerate(spec['release_id']['historical'] + [a.release_id])}
    key_rel = (vh_rel.assign(_o=vh_rel._rel.map(order)).sort_values('_o', kind='mergesort').groupby(['sample_key', 'field_name'])._rel.last())
    key_rel = key_rel[key_rel != '1.0.0']

    def add_cols(df, rel):
        df = df.copy()
        df[RA] = rel
        df[RR] = pd.Series([None] * len(df), dtype='object')
        df[PA] = df[RA]
        return df

    sd = pd.read_parquet(src / 'sample_determinations.parquet')
    rel = pd.Series('1.0.0', index=sd.index, dtype='object')
    idx = pd.MultiIndex.from_frame(sd[['sample_key', 'field_name']])
    hit = idx.isin(key_rel.index)
    rel[hit] = key_rel.reindex(idx[hit]).values
    sd2 = add_cols(sd, rel.values)
    sd2.to_parquet(out / 'sample_determinations.parquet', index=False)
    retired = vh_rel.rename(columns={'reason': C['retired_reason'], 'change_stage': C['retired_change_stage']})
    retired[RA] = '1.0.0'
    retired[RR] = retired._rel
    retired[PA] = retired[RA]
    cols_all = list(sd.columns) + [RA, RR, PA, C['retired_reason'], C['retired_change_stage']]
    for c in cols_all:
        if c not in retired.columns:
            retired[c] = None
    cur = sd2.copy()
    cur[C['retired_reason']] = None
    cur[C['retired_change_stage']] = None
    sd_all = pd.concat([cur[cols_all], retired[cols_all]], ignore_index=True)
    sd_all = sd_all.sort_values(['sample_key', 'field_name', RA, RR], kind='mergesort', na_position='first').reset_index(drop=True)
    sd_all.to_parquet(out / spec['files']['determinations_all'], index=False)

    uni = pd.read_parquet(src / 'universe_studies_all.parquet')
    svh = pd.read_parquet(src / 'study_verdict_history.parquet')
    hr = set(svh.loc[svh.stage_level == 'human_review', 'study_accession'])
    uni2 = add_cols(uni, uni.study_accession.map(lambda s: '1.1.0' if s in hr else '1.0.0').values)
    uni2.to_parquet(out / 'universe_studies_all.parquet', index=False)

    for name in spec['fact_tables']:
        if name in ('sample_determinations.parquet', 'universe_studies_all.parquet'):
            continue
        rel = '1.2.0' if name.startswith('sandpiper') else '1.0.0'
        if name.endswith('.parquet'):
            add_cols(pd.read_parquet(src / name), rel).to_parquet(out / name, index=False)
        else:
            add_cols(pd.read_csv(src / name, dtype=str, keep_default_na=False), rel).to_csv(out / name, index=False)

    sw = pd.read_parquet(src / 'sample_metadata_wide.parquet', columns=['catalog_scope', 'study_accession', 'sandpiper_version'])
    st = pd.read_parquet(src / 'study_metadata_wide.parquet', columns=['study_accession'])
    spv = str(sw.sandpiper_version.dropna().iloc[0]) if sw.sandpiper_version.notna().any() else ''
    cur_counts = dict(n_studies_included=len(st), n_samples=len(sw), n_catalog_scope=int(sw.catalog_scope.fillna(False).astype(bool).sum()),
                      n_determinations_current=int((sd_all[RR].isna()).sum()))
    rows = [
        dict(release_id='1.0.0', package_version='1.0.0', release_date='2026-09-25', data_tag='', site_tag='', doi='', notes_file='CHANGELOG.md'),
        dict(release_id='1.1.0', package_version='1.1.0', release_date='2026-09-25', data_tag='', site_tag='', doi='', notes_file='CHANGELOG.md'),
        dict(release_id='1.2.0', package_version='1.2.0', release_date='2026-09-26', data_tag='data-v1.2.0', site_tag='site-v1.2.0', doi='', n_samples=154206, n_determinations_current=618898, sandpiper_version=spv, notes_file='CHANGELOG.md'),
        dict(release_id='1.2.1', package_version='1.2.1', release_date='2026-09-26', data_tag='data-v1.2.1', site_tag='site-v1.2.1', doi='', n_catalog_scope=71795, sandpiper_version=spv, notes_file='CHANGELOG.md'),
        dict(release_id='1.2.2', package_version='1.2.2', release_date='2026-09-26', data_tag='data-v1.2.2', site_tag='site-v1.2.2', doi='', sandpiper_version=spv, notes_file='CHANGELOG.md', **cur_counts),
        dict(release_id=a.release_id, package_version=a.package_version, release_date=a.release_date, data_tag=f'data-v{a.package_version}', site_tag=f'site-v{a.package_version}', doi='',
             sandpiper_version=spv, notes_file=spec['files']['release_notes_pattern'].format(release_id=a.release_id), **cur_counts),
    ]
    reg = pd.DataFrame(rows, columns=spec['registry_columns'])
    for c in ['n_studies_included', 'n_samples', 'n_catalog_scope', 'n_determinations_current']:
        reg[c] = reg[c].astype('Int64')
    reg.to_csv(out / spec['files']['registry'], index=False)

    notes = out / spec['files']['release_notes_pattern'].format(release_id=a.release_id)
    notes.write_text(f"""# Release notes — {a.release_id} (data package {a.package_version}, {a.release_date})

*MOCK release notes written by site_generator/gen/tests/make_mock_release_package.py; the Data track's `make release` writes the real file.*

## New studies
No new studies in this mock (placeholder seeding; see releases.csv).

## Coverage
Not computed in the mock.

## Verdict changes
Placeholder seeding: verdict rows of studies with a human_review stage carry release_added 1.1.0.

## Findings applied
Placeholder: owner_decision rows -> 1.2.2; auditor_review:* rows -> 1.2.1.

## Sandpiper
Sandpiper {spv} rows carry release_added 1.2.0.

## Gold metrics
Not computed in the mock.

## Schema
Columns {RA}, {RR}, {PA} appended to every fact table; new files {spec['files']['determinations_all']} and {spec['files']['registry']}.
""", encoding='utf-8')

    vj = json.loads((src / 'VERSION.json').read_text())
    vj['previous_version'] = vj['package_version']
    vj['package_version'] = a.package_version
    vj['release_tag'] = f'data-v{a.package_version}'
    vj['release_id'] = a.release_id
    vj['previous_release_id'] = '1.2.2'
    vj['build_date'] = a.release_date
    vj['mock'] = 'placeholder release columns — site_generator/gen/tests/make_mock_release_package.py'
    for f in sorted(out.iterdir()):
        if f.name in ('VERSION.json', 'build_counts.json') or f.suffix not in ('.parquet', '.csv', '.gz', '.json', '.ipynb', '.md'):
            continue
        rows_n = vj['tables'].get(f.name, {}).get('rows')
        if f.suffix == '.parquet':
            import pyarrow.parquet as pq
            rows_n = int(pq.ParquetFile(f).metadata.num_rows)
        elif f.suffix == '.csv':
            rows_n = int(len(pd.read_csv(f, usecols=[0])))
        vj['tables'][f.name] = dict(vj['tables'].get(f.name, {}), sha256=sha256(f), rows=rows_n)
    (out / 'VERSION.json').write_text(json.dumps(vj, indent=1, sort_keys=True), encoding='utf-8')
    (out / 'build_counts.json').write_text(json.dumps(dict(package_version=a.package_version, release_id=a.release_id, **cur_counts), indent=1, sort_keys=True), encoding='utf-8')
    readme = (out / 'README.md').read_text(encoding='utf-8').replace('data package v1.2.0', f'data package v{a.package_version}', 1)
    (out / 'README.md').write_text(readme, encoding='utf-8')
    summary = dict(out=str(out), n_det_current=int(sd_all[RR].isna().sum()), n_det_retired=int(sd_all[RR].notna().sum()),
                   det_release_added=sd2[RA].value_counts().to_dict(), all_release_retired={str(k): int(v) for k, v in sd_all[RR].value_counts(dropna=False).items()},
                   uni_release_added=uni2[RA].value_counts().to_dict(), registry_rows=len(reg))
    print(json.dumps(summary, default=str, sort_keys=True))


if __name__ == '__main__':
    main()

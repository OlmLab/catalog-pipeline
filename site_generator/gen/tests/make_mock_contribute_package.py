#!/usr/bin/env python
"""Build a MOCK 1.4.0 (R2026.2) package from an unpacked 1.3.0 package by adding the two contribution-worklist tables
in the FROZEN schema of config/contribute.yaml. Used by the Site track to develop and test contribute/ before the Data
track's real `src/catalog/contribute/build_worklist.py` output exists. Nothing here is a curated value.

Usage: python make_mock_contribute_package.py --src data/inputs/data_package --out build/mock_package_1.4.0

PLACEHOLDER rules (NOT the Data track's rules — documented so the merge can drop them):
  * open study = included (study_metadata_wide) or uncertain (universe triage_verdict) with >= 1 of the six fields
    below missing_threshold on catalog_scope coverage. Coverage = study_field_coverage_matrix row when present, else the
    cov_* column of study_metadata_wide (18 included studies lack a matrix row), else 0 (uncertain studies).
  * blocker_code = no_linked_paper when the study has 0 rows in study_paper_links, controlled_access when
    study_metadata_wide.controlled_access, archive_only_uncertain for uncertain studies, else partial_coverage.
  * best_tier_* = recov_* of study_metadata_wide / universe (R0 when missing); blocker_detail / unlock_text from fixed
    templates; contribution_type paper_pointer for no_linked_paper, verdict_evidence for archive_only_uncertain,
    per_sample_table otherwise; own_data_pmids = all linked pmids; n_supp_tables_inventoried = 0.
"""
import argparse, hashlib, json, math, sys
from pathlib import Path
from urllib.parse import quote
import pandas as pd
import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def build_issue_url(cfg, acc, ctype, release_id):
    f = cfg['issue_form']
    title = quote(f['title'].format(study_accession=acc, contribution_type=ctype), safe='')
    return f['url_template'].format(repo=f['repo'], template=f['template'], label=f['label'], title=title,
                                    study_accession=acc, contribution_type=ctype, release_id=release_id)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--config', default=str(REPO / 'config' / 'contribute.yaml'))
    ap.add_argument('--releases-config', default=str(REPO / 'config' / 'releases.yaml'))
    ap.add_argument('--release-date', default='2026-10-24')
    a = ap.parse_args()
    src, out = Path(a.src), Path(a.out)
    cfg = yaml.safe_load(open(a.config))
    rspec = yaml.safe_load(open(a.releases_config))
    RID, PV = cfg['release_id'], str(cfg['package_version'])
    RA, RR, PA = rspec['columns']['release_added'], rspec['columns']['release_retired'], rspec['columns']['package_added']
    out.mkdir(parents=True, exist_ok=True)
    for f in sorted(src.iterdir()):
        if f.is_file():
            (out / f.name).write_bytes(f.read_bytes())

    st = pd.read_parquet(src / 'study_metadata_wide.parquet')
    uni = pd.read_parquet(src / 'universe_studies_all.parquet')
    uni = uni[uni[RR].isna()] if RR in uni.columns else uni
    mat = pd.read_csv(src / 'study_field_coverage_matrix.csv').set_index('study_accession')
    spl = pd.read_csv(src / 'study_paper_links.csv', dtype={'paper_id': str})
    sw = pd.read_parquet(src / 'sample_metadata_wide.parquet', columns=['study_accession', 'catalog_scope'] + list(cfg['fields'].values()))
    cs = sw[sw.catalog_scope.fillna(False).astype(bool)]
    n_with = {f: cs.groupby('study_accession')[f].apply(lambda x: int(x.notna().sum())) for f in cfg['fields'].values()}
    papers = spl.groupby('study_accession').pmid.apply(lambda x: ';'.join(sorted({str(int(v)) for v in x.dropna()})))
    n_papers = spl.groupby('study_accession').size()
    FIELDS, W, THR = cfg['fields'], cfg['field_weights'], float(cfg['missing_threshold'])
    L = cfg['text_limits']

    candidates = []
    for r in st.to_dict('records'):
        candidates.append(dict(r, _verdict='include', _cov_src='matrix' if r['study_accession'] in mat.index else 'wide'))
    unc = uni[(uni.triage_verdict == 'uncertain') & ~uni.study_accession.isin(set(st.study_accession))]
    for r in unc.to_dict('records'):
        candidates.append(dict(r, _verdict='uncertain', _cov_src='none', n_catalog_scope=0, controlled_access=r.get('controlled_access')))

    rows, frows = [], []
    for c in candidates:
        acc = c['study_accession']
        ncs = int(c.get('n_catalog_scope') or 0)
        cov, tier = {}, {}
        for k, f in FIELDS.items():
            if c['_cov_src'] == 'matrix':
                v = mat.at[acc, f]
            elif c['_cov_src'] == 'wide':
                v = c.get(f'cov_{f}')
            else:
                v = 0.0
            cov[k] = 0.0 if v is None or (isinstance(v, float) and math.isnan(v)) else float(v)
            t = c.get(f'recov_{k}')
            tier[k] = 'R0' if t is None or (isinstance(t, float) and math.isnan(t)) or t == '' else str(t)
        missing = [FIELDS[k] for k in FIELDS if cov[k] < THR]
        if not missing:
            continue
        npap = int(n_papers.get(acc, 0))
        ca = bool(c.get('controlled_access')) if c.get('controlled_access') is not None and c.get('controlled_access') == c.get('controlled_access') else False
        if c['_verdict'] == 'uncertain':
            blocker, ctype = 'archive_only_uncertain', 'verdict_evidence'
            detail = 'Triage could not decide whether this deposit is infant gut shotgun metagenomics; no per-sample metadata extracted.'
            unlock = 'Point to the study paper (PMID/DOI) or quote the archive/paper text that states the subjects are infants and the assay is shotgun metagenomics.'
        elif npap == 0:
            blocker, ctype = 'no_linked_paper', 'paper_pointer'
            detail = 'No paper is linked to this BioProject, so no supplementary table or methods text could be searched.'
            unlock = 'Point to the paper that describes this deposit (PMID or DOI), or upload a per-sample table keyed by run accession (SRR/ERR/DRR) or BioSample (SAMN/SAMEA).'
        elif ca:
            blocker, ctype = 'controlled_access', 'per_sample_table'
            detail = 'Per-sample metadata is held under controlled access; only the public archive attributes were available.'
            unlock = 'Upload the publicly shareable per-sample fields (age, delivery, feeding) keyed by run accession, or confirm that only derived values may be published.'
        else:
            blocker, ctype = 'partial_coverage', 'per_sample_table'
            detail = f"{npap} linked paper(s) and archive attributes cover some fields; still missing: {', '.join(missing)}."
            unlock = 'Upload a per-sample table keyed by run accession (SRR/ERR/DRR) or BioSample (SAMN/SAMEA) with the missing fields, or a key file mapping the paper sample names to accessions.'
        score = sum(W[k] * (1 - cov[k]) * math.log10(ncs + 1) for k in FIELDS if FIELDS[k] in missing)
        rows.append(dict(
            study_accession=acc, study_title=c.get('study_title'), cohort_id=c.get('cohort_id'), cohort_name=c.get('cohort_name'),
            triage_verdict=c['_verdict'], n_samples=int(c.get('n_samples') or 0), n_catalog_scope=ncs,
            n_infant_samples_est=None if c.get('n_infant_samples_est') is None or c.get('n_infant_samples_est') != c.get('n_infant_samples_est') else int(c['n_infant_samples_est']),
            missing_fields=';'.join(missing), n_missing_fields=len(missing),
            **{f'coverage_{k}': round(cov[k], 4) for k in FIELDS}, **{f'best_tier_{k}': tier[k] for k in FIELDS},
            blocker_code=blocker, blocker_detail=detail[:L['blocker_detail']], unlock_text=unlock[:L['unlock_text']], contribution_type=ctype,
            n_linked_papers=npap, own_data_pmids=papers.get(acc, ''), n_supp_tables_inventoried=0, controlled_access=ca,
            priority_score=round(score, 4), ena_url=c.get('ena_url') or f'https://www.ebi.ac.uk/ena/browser/view/{acc}',
            ncbi_url=c.get('ncbi_url') or f'https://www.ncbi.nlm.nih.gov/bioproject/{acc}', issue_url=build_issue_url(cfg, acc, ctype, RID),
            release_added=RID, release_retired=None, package_added=PV))
        for k, f in FIELDS.items():
            frows.append(dict(study_accession=acc, field=f, coverage=round(cov[k], 4), n_with_value=int(n_with[f].get(acc, 0)), n_catalog_scope=ncs,
                              best_tier=tier[k], blocker_code=('complete' if cov[k] >= THR else blocker),
                              evidence=(f'mock: coverage {cov[k]:.2f} from {c["_cov_src"]}; tier {tier[k]}')[:L['evidence']],
                              release_added=RID, release_retired=None, package_added=PV))
    wl = pd.DataFrame(rows).sort_values(['priority_score', 'n_catalog_scope', 'study_accession'], ascending=[False, False, True], kind='mergesort').reset_index(drop=True)
    wl.insert(0, 'rank', range(1, len(wl) + 1))
    wl = wl[cfg['worklist_columns']]
    assert list(wl.columns) == cfg['worklist_columns']
    wl.to_csv(out / cfg['files']['worklist'], index=False)
    fl = pd.DataFrame(frows)[cfg['fields_columns']].sort_values(['study_accession', 'field'], kind='mergesort')
    fl.to_csv(out / cfg['files']['worklist_fields'], index=False)

    # releases.csv: append the R2026.2 row (counts copied from the previous row: nothing changes in the mock)
    reg = pd.read_csv(src / rspec['files']['registry'], dtype=str, keep_default_na=False)
    prev = reg.iloc[-1].to_dict()
    new = dict(prev, release_id=RID, package_version=PV, release_date=a.release_date, data_tag=f'data-v{PV}', site_tag=f'site-v{PV}', doi='',
               notes_file=rspec['files']['release_notes_pattern'].format(release_id=RID))
    reg = pd.concat([reg, pd.DataFrame([new])[reg.columns]], ignore_index=True)
    reg.to_csv(out / rspec['files']['registry'], index=False)
    notes = out / rspec['files']['release_notes_pattern'].format(release_id=RID)
    n_blk = wl.blocker_code.value_counts().to_dict()
    notes.write_text(f"""# Release notes — {RID} (data package {PV}, {a.release_date})

*MOCK release notes written by site_generator/gen/tests/make_mock_contribute_package.py; the Data track's `make release` writes the real file.*

## New tables
`contribute_worklist.csv` ({len(wl)} open studies) and `contribute_worklist_fields.csv` ({len(fl)} study × field rows) — the read-only contribution worklist (MATURITY_PLAN §3.2), schema `config/contribute.yaml`.

## Blockers (placeholder assignment)
{chr(10).join(f'* {k}: {v}' for k, v in sorted(n_blk.items()))}

## New studies
None in this mock.

## Verdict changes
None in this mock.
""", encoding='utf-8')
    vj = json.loads((src / 'VERSION.json').read_text())
    vj['previous_version'] = vj['package_version']
    vj['previous_release_id'] = vj['release_id']
    vj['package_version'] = PV
    vj['release_tag'] = f'data-v{PV}'
    vj['release_id'] = RID
    vj['build_date'] = a.release_date
    vj['mock'] = 'placeholder contribution worklist — site_generator/gen/tests/make_mock_contribute_package.py'
    import pyarrow.parquet as pq
    for f in sorted(out.iterdir()):
        if f.name in ('VERSION.json', 'build_counts.json') or f.suffix not in ('.parquet', '.csv', '.gz', '.json', '.ipynb', '.md'):
            continue
        rows_n = vj['tables'].get(f.name, {}).get('rows')
        if f.suffix == '.parquet':
            rows_n = int(pq.ParquetFile(f).metadata.num_rows)
        elif f.suffix == '.csv':
            rows_n = int(len(pd.read_csv(f, usecols=[0])))
        vj['tables'][f.name] = dict(vj['tables'].get(f.name, {}), sha256=sha256(f), rows=rows_n, size_bytes=f.stat().st_size)
    (out / 'VERSION.json').write_text(json.dumps(vj, indent=1, sort_keys=True), encoding='utf-8')
    readme = (out / 'README.md').read_text(encoding='utf-8').replace(f"data package v{vj['previous_version']}", f'data package v{PV}', 1)
    (out / 'README.md').write_text(readme, encoding='utf-8')
    summary = dict(out=str(out), n_worklist=len(wl), n_fields_rows=len(fl), blockers=n_blk, verdicts=wl.triage_verdict.value_counts().to_dict(),
                   n_samples_affected=int(wl.n_samples.sum()), n_catalog_scope_affected=int(wl.n_catalog_scope.sum()),
                   cov_source={k: int(v) for k, v in pd.Series([c['_cov_src'] for c in candidates]).value_counts().items()}, registry_rows=len(reg))
    print(json.dumps(summary, default=str, sort_keys=True))


if __name__ == '__main__':
    main()

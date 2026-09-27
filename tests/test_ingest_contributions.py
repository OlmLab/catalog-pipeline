"""ingest_contributions: form-body parsing, attachment discovery, type/size gates, deterministic joinability, verdicts.

Package-backed tests run against CATALOG_PACKAGE_DIR (an unpacked >= 1.3.0 package or the mock 1.4.0 package) when set;
the pure-function tests always run. The fake downloader serves bytes from a dict — no network.
"""
import io, json, os, sys
from pathlib import Path
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'src'))
from catalog.contribute import ingest_contributions as IC  # noqa: E402

CFG = IC.load_cfg(REPO / 'config' / 'contribute.yaml')
ING = CFG['ingest']
PKG = Path(os.environ['CATALOG_PACKAGE_DIR']) if os.environ.get('CATALOG_PACKAGE_DIR') else None
needs_pkg = pytest.mark.skipif(PKG is None or not (PKG / 'runs.parquet').exists(), reason='set CATALOG_PACKAGE_DIR to an unpacked package')

BODY = """### study_accession

{acc}

### contribution_type

per_sample_table

### source

journal_supplement_url

### source_url

https://doi.org/10.1000/example

### licence

- [x] I confirm the uploaded table may be redistributed under CC-BY-4.0, or I ask that only derived values be published

### note

Column `run` holds SRR accessions; ages in days. Contact: someone@example.org
{links}

### release_tag

R2026.2
"""


def issue(n, acc, links, login='contributor1'):
    return dict(number=n, title=f'[contribution] {acc}: per_sample_table', html_url=f'https://github.com/OlmLab/infant-gut-catalog/issues/{n}',
                created_at='2026-10-25T10:00:00Z', user=dict(login=login), body=BODY.format(acc=acc, links='\n'.join(links)))


def test_parse_form_body_and_attachments():
    form = IC.parse_form_body(BODY.format(acc='PRJNA1', links='[t.csv](https://github.com/user-attachments/files/1/t.csv)'), CFG['issue_form']['field_ids'])
    assert form['study_accession'] == 'PRJNA1' and form['contribution_type'] == 'per_sample_table' and form['source'] == 'journal_supplement_url'
    assert '[x]' in form['licence'] and form['release_tag'] == 'R2026.2'
    urls = IC.find_attachments('see https://github.com/user-attachments/files/1/t.csv and https://github.com/user-attachments/assets/abc-def and '
                               '![img](https://user-images.githubusercontent.com/1/x.png) but not https://example.org/evil.sh')
    assert urls == ['https://github.com/user-attachments/assets/abc-def', 'https://github.com/user-attachments/files/1/t.csv', 'https://user-images.githubusercontent.com/1/x.png']


def test_type_and_size_gates():
    for bad in ['https://github.com/user-attachments/files/1/run.exe', 'https://github.com/user-attachments/files/1/tab.zip', 'https://github.com/user-attachments/files/1/x.py',
                'https://github.com/user-attachments/files/1/x.gz', 'https://github.com/user-attachments/files/1/x.sh', 'https://github.com/user-attachments/assets/no-extension']:
        assert IC.check_file(bad, b'a,b\n1,2\n', ING, {}, {})['verdict'] == 'rejected'
    big = IC.check_file('https://github.com/user-attachments/files/1/t.csv', b'x' * (ING['max_bytes'] + 1), ING, {}, {})
    assert big['verdict'] == 'rejected' and '50 MB' in big['reason']
    assert IC.check_file('https://github.com/user-attachments/files/1/t.csv', None, ING, {}, {}, err='HTTPError: 404')['verdict'] == 'rejected'
    assert IC.check_file('https://github.com/user-attachments/files/1/t.csv', b'', ING, {}, {})['verdict'] == 'rejected'  # no rows


def test_joinability_synthetic_keys():
    keys = {k: set() for k in IC.KEY_TYPES}
    keys['run_accession'] = {f'SRR{100000 + i}' for i in range(40)}
    keys['sample_title'] = {f'T1_S{i}' for i in range(40)}
    good = pd.DataFrame({'run': [f'SRR{100000 + i}' for i in range(30)], 'age_days': [str(i) for i in range(30)]})
    j = IC.joinability(good, keys, ING['min_matches'], ING['match_fraction'])
    assert j['joinable'] and j['best']['column'] == 'run' and j['best']['key_type'] == 'run_accession' and j['best']['matches'] == 30 and j['threshold'] == 20
    few = pd.DataFrame({'run': [f'SRR{100000 + i}' for i in range(10)] + [f'SRR9{i:05d}' for i in range(20)], 'v': ['1'] * 30})
    j = IC.joinability(few, keys, ING['min_matches'], ING['match_fraction'])
    assert not j['joinable'] and j['best']['matches'] == 10  # 10 < max(20, 15)
    unj = pd.DataFrame({'sample': [f'P{i}_V{i % 3}' for i in range(30)], 'delivery': ['vaginal'] * 30})
    j = IC.joinability(unj, keys, ING['min_matches'], ING['match_fraction'])
    assert not j['joinable'] and j['top3'][0]['column'] == 'sample' and j['top3'][0]['form'] == 'subject_timepoint'
    assert IC.id_form([f'SRR{100000 + i}' for i in range(5)]) == 'run_accession' and IC.id_form(['SAMN01234567']) == 'biosample'


def test_verdict_priority_and_duplicate():
    data = b'run,age\n' + b''.join(f'SRR{100000 + i},{i}\n'.encode() for i in range(30))
    keys = {k: set() for k in IC.KEY_TYPES}
    keys['run_accession'] = {f'SRR{100000 + i}' for i in range(40)}
    first = IC.check_file('https://github.com/user-attachments/files/1/t.csv', data, ING, {}, keys)
    assert first['verdict'] == 'accepted_for_review'
    dup = IC.check_file('https://github.com/user-attachments/files/2/t.csv', data, ING, {first['sha256']: 7}, keys)
    assert dup['verdict'] == 'duplicate_of_existing' and '#7' in dup['reason']
    xlsx = io.BytesIO()
    with pd.ExcelWriter(xlsx) as w:
        pd.DataFrame({'note': ['a', 'b']}).to_excel(w, sheet_name='readme', index=False)
        pd.read_csv(io.BytesIO(data)).to_excel(w, sheet_name='samples', index=False)
    x = IC.check_file('https://github.com/user-attachments/files/3/t.xlsx', xlsx.getvalue(), ING, {}, keys)
    assert x['verdict'] == 'accepted_for_review' and set(x['tables']) == {'readme', 'samples'} and x['tables']['samples']['joinable']


@needs_pkg
def test_process_issue_against_package(tmp_path):
    runs = pd.read_parquet(PKG / 'runs.parquet', columns=['study_accession', 'run_accession'])
    acc = runs.groupby('study_accession').size().sort_values(ascending=False).index[0]
    srr = sorted(runs.loc[runs.study_accession == acc, 'run_accession'])[:60]
    good = ('run_accession,age_days,delivery_mode\n' + ''.join(f'{r},{i},vaginal\n' for i, r in enumerate(srr))).encode()
    unj = ('sample,age_days\n' + ''.join(f'T1_S{i},{i}\n' for i in range(60))).encode()
    files = {'https://github.com/user-attachments/files/11/good.csv': good, 'https://github.com/user-attachments/files/12/unj.tsv': unj.replace(b',', b'\t'),
             'https://github.com/user-attachments/files/13/dup.csv': good}

    def fake_dl(url, token=None, max_bytes=None):
        return files[url]
    out = tmp_path / 'contributions'
    r1 = IC.process_issue(issue(1, acc, ['[good.csv](https://github.com/user-attachments/files/11/good.csv)']), PKG, out, CFG, downloader=fake_dl)
    assert r1['verdict'] == 'accepted_for_review' and r1['study_in_package'] and r1['files'][0]['tables']['table']['best']['key_type'] == 'run_accession'
    assert r1['files'][0]['tables']['table']['best']['matches'] == 60
    seen = IC.scan_seen(out)
    r2 = IC.process_issue(issue(2, acc, ['[unj.tsv](https://github.com/user-attachments/files/12/unj.tsv)', '[bad.sh](https://github.com/user-attachments/files/12/bad.sh)']), PKG, out, CFG, downloader=fake_dl, seen_sha=seen)
    assert r2['verdict'] == 'unjoinable' and [f['verdict'] for f in r2['files']] == ['rejected', 'unjoinable']
    assert r2['files'][1]['tables']['table']['top3'][0]['form'] == 'subject_timepoint'
    r3 = IC.process_issue(issue(3, acc, ['[dup.csv](https://github.com/user-attachments/files/13/dup.csv)']), PKG, out, CFG, downloader=fake_dl, seen_sha=seen)
    assert r3['verdict'] == 'duplicate_of_existing'
    r4 = IC.process_issue(issue(4, 'PRJNA000000000', []), PKG, out, CFG, downloader=fake_dl)
    assert r4['verdict'] == 'rejected' and r4['no_attachment'] and r4['study_in_package'] is False
    for n in (1, 2, 3, 4):
        man = json.loads((out / str(n) / 'manifest.json').read_text())
        assert 'example.org' not in json.dumps(man) and '@' not in json.dumps(man) and man['uploader'] == 'contributor1'
        assert (out / str(n) / 'REPORT.md').exists() and (out / str(n) / 'report.json').exists()
    assert (out / '1' / 'good.csv').read_bytes() == good and not (out / '2' / 'bad.sh').exists()
    md = (out / '2' / 'REPORT.md').read_text()
    assert 'unjoinable' in md and 'subject_timepoint' in md and 'key file' in md

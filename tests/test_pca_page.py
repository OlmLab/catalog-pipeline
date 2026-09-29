"""Standalone harness for site_generator/gen/pages/pca.py: build the Atlas › PCA page from a synthetic 500-sample input
and assert the data files exist, the binary layout matches pca_meta.json, and the HTML carries the selectors.
Run: python -m pytest tests/test_pca_page.py"""
import json
import struct
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from jinja2 import Environment, FileSystemLoader, select_autoescape

GEN = Path(__file__).resolve().parents[1] / 'site_generator' / 'gen'
sys.path.insert(0, str(GEN))
from pages import pca  # noqa: E402

N = 500


def _fmt(v):
    try:
        return f'{int(v):,}'
    except (TypeError, ValueError):
        return str(v)


def make_env():
    env = Environment(loader=FileSystemLoader(GEN / 'templates'), autoescape=select_autoescape(['html']))
    env.filters.update(fmt=_fmt, numint=_fmt, pct=lambda v: f'{100 * v:.0f} %', pct1=lambda v: f'{100 * v:.1f} %', num2=lambda v: f'{v:.2f}')
    env.globals.update(site=dict(title='Test Catalog', short_title='Test', description='d', release_tag='t', release_id='R0', version='0.0.0', build_date='2026-01-01',
                                 base_url='https://example.org/', sha8='deadbeef', doi='', has_contribute=False, contribute_page='', issue_repo='', sri={}, nav=[('home','Home','index.html'),('atlas','Atlas','atlas/index.html')], citation='c', issue_template='', issue_label='',
                                 about=dict(lab_name='Lab', lab_url='https://example.org/lab', funder_name='Funder', funder_url='https://example.org/f')))
    return env


def synthetic(seed=0):
    rng = np.random.default_rng(seed)
    keys = [f'SAMN{i:08d}' for i in range(N)]
    studies = [f'PRJNA{100 + (i % 25):04d}' for i in range(N)]
    scores = pd.DataFrame({'sample_key': keys, **{f'pc{j}': rng.normal(size=N).astype('float32') for j in range(1, 6)}})
    genera = [f'g__G{k}' for k in range(40)]
    loadings = pd.DataFrame({'genus': genera, **{f'pc{j}': rng.normal(size=40) for j in range(1, 6)}})
    variance = pd.DataFrame({'pc': [f'pc{j}' for j in range(1, 6)], 'explained_variance_ratio': [0.2, 0.1, 0.05, 0.03, 0.02], 'singular_value': [5, 4, 3, 2, 1]})
    wide = pd.DataFrame({'sample_key': keys, 'study_accession': studies,
                         'age_category': rng.choice(['infant', 'child', 'adult', None], size=N),
                         'country': rng.choice([f'C{k}' for k in range(30)] + [None], size=N),
                         'health_condition': rng.choice(['healthy', 'ibd', None], size=N),
                         'body_site_class': rng.choice(['primary', 'unknown'], size=N),
                         'lifestyle': rng.choice(['industrialised', 'rural', None], size=N)})
    # a few catalog samples without scores
    wide = pd.concat([wide, pd.DataFrame({'sample_key': ['SAMN99999999'], 'study_accession': ['PRJNA0000']})], ignore_index=True)
    summ = pd.DataFrame({'sample_key': keys, 'top_genus': rng.choice(genera[:6], size=N)})
    st = pd.DataFrame({'study_accession': sorted(set(studies)), 'study_title': ['Title ' + s for s in sorted(set(studies))]})
    return dict(wide=wide, studies=st, pca_scores=scores, pca_loadings=loadings, pca_variance=variance, sp_summary=summ,
                pca_method=dict(root_min=2, prevalence_pct=1, pseudocount='1e-5'))


def build_once(tmp_path):
    env = make_env(); written = []

    def render(tpl, path, root, nav=None, crumbs=None, **ctx):
        html = env.get_template(tpl).render(root=root, nav=nav, crumbs=crumbs, page_path=path, **ctx)
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(html, encoding='utf-8'); written.append((path, root, nav))
    res = pca.build(env, render, synthetic(), tmp_path)
    return res, written


def test_files_and_layout(tmp_path):
    res, written = build_once(tmp_path)
    assert written == [('atlas/pca.html', '../', 'atlas')]
    d = tmp_path / 'data' / 'atlas'
    for f in ('pca_points.bin', 'pca_codes.bin', 'pca_meta.json'):
        assert (d / f).exists(), f
    meta = json.loads((d / 'pca_meta.json').read_text())
    assert meta['n_points'] == N == res['n_points']
    assert (d / 'pca_points.bin').stat().st_size == N * meta['n_pcs'] * 4
    codes_len = sum(N * (2 if f['dtype'] == 'uint16' else 1) for f in meta['fields'])
    assert (d / 'pca_codes.bin').stat().st_size == codes_len
    assert len(meta['keys'].split('\n')) == N
    # codes decode to labels; study field keeps every study, last two labels are other / (no value)
    buf = (d / 'pca_codes.bin').read_bytes()
    for f in meta['fields']:
        fmt = '<' + str(N) + ('H' if f['dtype'] == 'uint16' else 'B')
        vals = struct.unpack_from(fmt, buf, f['offset'])
        assert max(vals) < len(f['labels']), f['field']
        assert f['labels'][-2:] == ['other', '(no value)']
        assert sum(f['counts']) == N
    sf = next(f for f in meta['fields'] if f['field'] == 'study_accession')
    assert len(sf['labels']) == 25 + 2
    assert [f['field'] for f in meta['fields']] == ['study_accession', 'age_category', 'country', 'health_condition', 'body_site_class', 'top_genus', 'lifestyle']
    assert abs(sum(p['explained_variance_ratio'] for p in meta['pcs']) - 0.40) < 1e-9
    assert res['total_bytes'] <= pca.MAX_TOTAL_BYTES


def test_html_selectors(tmp_path):
    build_once(tmp_path)
    html = (tmp_path / 'atlas' / 'pca.html').read_text()
    for sel in ('id="pca-x"', 'id="pca-y"', 'id="pca-color"', 'id="pca-study"', 'id="pca-canvas"', 'id="pca-legend"', 'id="pca-selection"'):
        assert sel in html, sel
    for opt in ('value="age_category"', 'value="country"', 'value="health_condition"', 'value="body_site_class"', 'value="top_genus"', 'value="study_accession"', 'value="lifestyle"'):
        assert opt in html, opt
    assert html.count('<option value="0"') == 2 and html.count('<option value="4"') == 2  # PC1..PC5 on both axes
    assert 'PC1 20.0 %' in html and 'five components together 40.0 %' in html
    assert 'pca_points.bin' in html and 'pca_codes.bin' in html and 'pca_meta.json' in html  # layout documented in the footer
    assert 'static/pca.js' in html and 'static/pca.css' in html
    assert 'href="../index.html"' in html  # root='../' resolved


def test_lifestyle_optional(tmp_path):
    ctx = synthetic(); ctx['wide'] = ctx['wide'].drop(columns=['lifestyle'])
    env = make_env()
    render = lambda tpl, path, root, nav=None, crumbs=None, **c: (tmp_path / path).parent.mkdir(parents=True, exist_ok=True) or (tmp_path / path).write_text(env.get_template(tpl).render(root=root, nav=nav, crumbs=crumbs, page_path=path, **c))
    res = pca.build(env, render, ctx, tmp_path)
    assert 'lifestyle' not in res['fields']
    assert 'value="lifestyle"' not in (tmp_path / 'atlas' / 'pca.html').read_text()


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))

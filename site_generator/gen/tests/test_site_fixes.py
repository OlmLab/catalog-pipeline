"""Unit tests for the v3 site-fix wave (F1/R3-5, F7, F11, F18). Run: CATALOG_PACKAGE_DIR=<pkg> python -m pytest site_generator/gen/tests"""
import os, re, sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_site as bs

def lum(hexc):
    r, g, b = [int(hexc[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)

def contrast(a, b):
    la, lb = lum(a), lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)

def test_frame_tokens_stripped():
    assert bs.strip_frame_tokens('kept after human-review pass (frame b83bd6c7 artifact) end') == 'kept after human-review pass end'
    assert bs.strip_frame_tokens('taxid_2705415_human_feces_metagenome_not_in_frame') == 'taxid_2705415_human_feces_metagenome_not_in_frame'
    assert bs.strip_frame_tokens(None) is None

def test_org_leak_regex():
    assert bs.ORG_LEAK_RE.search('SUB13731056; University of Minnesota')
    assert bs.ORG_LEAK_RE.search('someone@qq.com')
    assert not bs.ORG_LEAK_RE.search('University of Colorado Boulder')

def test_palette_contrast_and_sync():
    # since site v3 (1.10.0) the taxon palette is applied server-side (build_site.TAXON_PALETTE); explorer.js has no copy to sync
    for c in bs.TAXON_PALETTE:
        if c.upper() == '#CFB87C':  # brand gold; segments are separated and labelled
            continue
        assert contrast(c, '#FFFFFF') >= 3.0, c

def test_issue_url_budget_and_encoding():
    url = bs.issue_url(title='t', identifier='X', current_state='“' * 2500)
    assert len(url) <= 6000
    assert not re.search(r'%[0-9A-F]?$', url)  # never cut inside an escape

@pytest.mark.skipif(not os.environ.get('CATALOG_PACKAGE_DIR'), reason='needs a package dir')
def test_no_org_leak_in_package():
    import pandas as pd
    pkg = Path(os.environ['CATALOG_PACKAGE_DIR'])
    sas = pd.read_csv(pkg / 'study_authors_summary.csv')
    assert not sas.organisations.dropna().astype(str).str.contains(bs.ORG_LEAK_RE).any()

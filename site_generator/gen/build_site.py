#!/usr/bin/env python
"""Static site generator v2 for the Infant Gut Shotgun-Metagenome Catalog.

Usage:  python build_site.py --package PKG_DIR --out site [--reports DIR] [--package-zip ZIP] [--base-url URL]
                             [--config ../../config/site.yaml] [--allow-placeholder-base-url]

Every number, accession and identifier on the site is read from the package tables; nothing is hard-coded.
Deterministic (A2): build date = VERSION.json build_date (never wall clock); every *.csv.gz is written with gzip
mtime=0; all iteration is over sorted keys; JSON is dumped with sort_keys. Two builds from the same package are
byte-identical (tests/test_build_determinism.py).
"""
import argparse, gzip, hashlib, io, json, math, os, re, shutil, sys, time
from pathlib import Path
from urllib.parse import quote
import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape
import markdown
import yaml

HERE = Path(__file__).resolve().parent
FIELDS = ['probiotic_exposure', 'preterm_status', 'gestational_age_weeks', 'delivery_mode', 'feeding_mode',
          'antibiotic_exposure', 'age_at_collection_days', 'birth_weight_grams', 'country', 'maternal_antibiotics',
          'hmo_supplementation', 'nec_status', 'health_condition', 'multiple_birth', 'sibling_in_study',
          'geo_subregion', 'sex', 'timepoint_label', 'subject_id']
COV_FIELDS = ['age_at_collection_days', 'delivery_mode', 'feeding_mode', 'preterm_status', 'antibiotic_exposure',
              'gestational_age_weeks', 'birth_weight_grams', 'probiotic_exposure', 'maternal_antibiotics',
              'hmo_supplementation', 'nec_status', 'country', 'health_condition', 'multiple_birth',
              'sibling_in_study', 'geo_subregion']
CAT_FIELDS = ['delivery_mode', 'feeding_mode', 'preterm_status', 'antibiotic_exposure', 'probiotic_exposure',
              'maternal_antibiotics', 'hmo_supplementation', 'nec_status', 'health_condition', 'multiple_birth',
              'sibling_in_study', 'sex']
LABELS = {f: f.replace('_', ' ').capitalize() for f in FIELDS}
LABELS.update({'age_at_collection_days': 'Age at collection (days)', 'gestational_age_weeks': 'Gestational age (weeks)',
               'birth_weight_grams': 'Birth weight (g)', 'hmo_supplementation': 'HMO supplementation',
               'nec_status': 'NEC status', 'geo_subregion': 'Geographic subregion'})
# B8 / Fields page: definition caveats per field (text, not numbers)
FIELD_CAVEATS = {
    'antibiotic_exposure': '= ANY antibiotics given to the infant before or at sampling (not current use). "no" means a source documents no exposure, not "no mention". R3 group statements ("all infants received empirical antibiotics") are applied to every sample of the group at scope=group.',
    'feeding_mode': 'Categories differ between sources (exclusive/predominant breastfeeding, mixed, formula); boolean feeding columns and "predominantly human milk" never become a value.',
    'preterm_status': 'term requires ≥37 weeks when derived from a criterion; "healthy infants" never implies term; 136 values are derived from gestational age.',
    'age_at_collection_days': 'Postnatal age in days at sample collection; ranges and timepoint lists are not values; corrected gestational age is a different field. Values > 1,100 d set adult_age_flag.',
    'gestational_age_weeks': 'GA at birth in completed weeks; maternal pregnancy-week sampling is not GA at birth; ±1 week tolerance in the gold evaluation.',
    'birth_weight_grams': 'No external truth set; blind model re-judgement only.',
    'probiotic_exposure': 'Any probiotic given to the infant; no external truth set (54 % of values came from one questionnaire-based deposit before the age-scope fix — filter on age_scope).',
    'maternal_antibiotics': 'Intrapartum or pregnancy antibiotics to the mother; no external truth set.',
    'hmo_supplementation': 'Human-milk-oligosaccharide-supplemented formula; no external truth set.',
    'nec_status': 'Necrotising enterocolitis diagnosis; absence of unrelated illness never implies nec_status=no.',
    'country': 'ISO-2 of the sampling country from archive attributes or paper text.',
    'health_condition': 'Extension field, one pass, less audited.', 'multiple_birth': 'Extension field, one pass, less audited.',
    'sibling_in_study': 'Extension field (family IDs), one pass, less audited.', 'geo_subregion': 'Extension field (UN M49 subregion of the country), one pass, less audited.',
    'sex': 'Archive attribute or table column; no external truth set.', 'subject_id': 'Submitter identifier or resolved subject key; not evaluated.', 'timepoint_label': 'Compact tokens (D6, M4, 6m) are labels, not ages, unless the study confirms the unit.',
}
FILE_DESC = {
    'sample_metadata_wide.parquet': 'Start here. One row per sample: identifiers, body-site class, age_scope, every metadata field with __confidence, __route and __scope, subject/timepoint, run accessions, cohort, Sandpiper sp_* columns, links.',
    'sample_metadata_wide.csv.gz': 'Same table as gzip-compressed CSV.',
    'sample_determinations.parquet': 'Long form: one row per sample × field with evidence_source, evidence_locator, evidence_quote (≤12 words verbatim), route, scope, confidence.',
    'study_metadata_wide.parquet': 'One row per included study (BioProject): title, counts, age_scope counts, triage evidence, recoverability tiers, per-field coverage (cov_*), cohort, Sandpiper coverage, authors, links.',
    'study_metadata_wide.csv': 'Same table as CSV.',
    'runs.parquet': 'Run → sample → study with library/instrument fields (join key into ENA/SRA).',
    'sample_subjects.parquet': 'Subject and timepoint resolution per sample (subject_key, role, t_index).',
    'cohorts.csv': 'Cohort clusters (studies + papers sharing a cohort) with unique-infant estimates.',
    'study_paper_links.csv': 'Study ↔ paper links with PMID/PMCID/DOI.',
    'universe_studies_all.parquet': 'Every screened study with verdict, reason code and evidence.',
    'human_review_queue.csv': 'Studies the pipeline could not decide, with the reason.',
    'field_coverage_summary.csv': 'Coverage per field (samples, studies, route counts).',
    'study_field_coverage_matrix.csv': 'Coverage per study × field.',
    'extraction_gold_eval_hires.csv': 'Precision/recall vs curatedMetagenomicData (hi-res gold).',
    'parent_biosamples.parquet': 'The 16 parent BioSamples of the run-level rows (provenance only; counted nowhere).',
    'study_verdict_history.parquet': 'Every triage-stage verdict per study with model, confidence, evidence, source table.',
    'value_history.parquet': 'Determinations that are not current (superseded, rejected, dropped …) with reason and replaced_by.',
    'sample_determinations_superseded.parquet': 'Subset of value_history in the v1.1 layout.',
    'confidence_tiers.csv': 'Engine confidence tiers: route × determiner × scope with the discrete values emitted.',
    'tier_field_precision.csv': 'Empirical precision of each route × confidence tier per field against the cMD gold join.',
    'sample_unit_classification.csv': 'Per-BioSample multi-run classification.', 'sample_unit_classification_by_study.csv': 'Per-study sample-unit class (A run-keyed, C technical, X cross-study).',
    'sandpiper_sample_summary.parquet': 'Sandpiper/SingleM per-sample summary (all sp_* columns, indicators, QC flags, URL).',
    'sandpiper_top_genera.parquet': 'Top-15 genera + unassigned bin per profiled sample (loaded on demand by the explorer).',
    'sandpiper_study_panels.parquet': 'Per-study mean top phyla / genera over profiled infant-scope samples (study-page panels).',
    'sandpiper_run_qc.parquet': 'All catalog runs: profiled or miss reason, QC fields and flags, Sandpiper URL.',
    'sandpiper_study_coverage.csv': 'Per study: runs/samples profiled and miss reasons.',
    'sandpiper_study_qc_flags.csv': 'Per study: flag fractions, medians, auditor attention.',
    'sandpiper_flag_definitions.json': "Sandpiper's published QC flag definitions.",
    'authors.parquet': 'Study × author × paper rows (string-matched names; see AUTHORS_REPORT).',
    'study_authors_summary.csv': 'Per screened study: first/last author, n authors, organisations.',
    'authors_index.json': 'Author search index used by the Authors page.',
    'sample_determinations_all.parquet': 'Bitemporal determinations: current rows (release_retired null) plus every retired row with release_added / release_retired / retired_reason / retired_change_stage (R2026.1).',
    'contribute_worklist.csv': 'Contribution worklist (R2026.2): one row per open study — missing fields, coverage, recoverability tiers, blocker code, unlock text, prefilled Issue URL.',
    'contribute_worklist_fields.csv': 'Contribution worklist, study × field: coverage, n_with_value, best tier, field-level blocker, evidence.',
    'releases.csv': 'Release registry: one row per release id (release date, package version, tags, DOI, headline counts).',
    'VERSION.json': 'Package version, release id, release tag, build date, sha256 + rows per table.',
    'DATA_DICTIONARY.md': 'Every column, every vocabulary.', 'README.md': 'Package overview and how to read a value.',
    'CHANGELOG.md': 'Version history.', 'getting_started.ipynb': 'Notebook: load, filter, join, plot.',
    'SANDPIPER_REPORT.md': 'Sandpiper join: source, method, validation, caveats.', 'AUTHORS_REPORT.md': 'Author index: sources, coverage, caveats.',
    'DATA_MODEL_FIX_REPORT.md': 'v1.2 data-model fix (age scope, parents, history).', 'EXTRACTION_REPORT.md': 'Per-sample extraction report.',
}
OFFSITE = [dict(name='sandpiper_profiles.parquet', desc='Full sample × rank × taxon profiles (coverage_filled, rel_abundance; 10.2 M rows, ≈100 MB) — GitHub Release asset data-v{v}, not on the site.'),
           dict(name='sandpiper_profiles_runs.parquet', desc='Per-run profiles as delivered by Sandpiper (10.4 M rows, ≈61 MB) — Release asset.'),
           dict(name='infant_catalog.sqlite', desc='All package tables as one SQLite database (≈200 MB) — Release asset.')]
# harmonised taxon palette (CU Boulder gold / grays + muted earth tones); labels always accompany colours
# F11: every non-brand swatch >= 3:1 against white (CU gold #CFB87C is kept as the brand colour; segments are separated by a #565A5C rule and always labelled)
TAXON_PALETTE = ['#CFB87C', '#565A5C', '#A88B4A', '#8C8F91', '#7A6A3C', '#3C3C3C', '#8A7A48', '#7F7060', '#6E6A5E', '#8F7418', '#6F6D62', '#6B6F73', '#7D7461', '#4A4A4A', '#75604A', '#5F6366']
UNASSIGNED_COLOR = '#D9D9D9'
ISSUE_REPO = 'https://github.com/OlmLab/infant-gut-catalog/issues/new'
ISSUE_TEMPLATE = 'catalog-finding.yml'
# F7: only these report documents may be published from --reports; internal planning docs stay in the repo.
PUBLIC_REPORT_DOCS = [('CATALOG_REPORT.md', 'Catalog report'), ('EXTRACTION_REPORT.md', 'Extraction report')]
NEVER_PUBLISH_DOCS = {'NEXT_STAGE.md', 'SCALE_UP_PLAN.md', 'RUNBOOK.md', 'STATE_BRIEF.md'}
# F7: internal session identifiers in free-text notes, e.g. '(frame b83bd6c7 artifact)' or 'frame b83bd6c7'
FRAME_TOKEN_RE = re.compile(r'\s*\((?:frame|session)\s+[0-9a-f]{6,}[^)]*\)|\b(?:frame|session)\s+[0-9a-f]{8,}\b')
# F1 / R3-5: no organisation string may carry an SRA submission id or an e-mail address
ORG_LEAK_RE = re.compile(r'SUB\d{6,}|@')
# F15: study-level recall is stated once, with both definitions, wherever it appears (README.md carries the same sentence).
GOLD_RECALL_SENTENCE = ('study-level recall on the 22 curatedMetagenomicData infant BioProjects: 17/22 by the automated cascade, '
                        '18/22 after the human-review pass (one study, decision_stage = session_model_review)')


def strip_frame_tokens(text):
    if isnull(text) or text == '':
        return text
    return re.sub(r'\s{2,}', ' ', FRAME_TOKEN_RE.sub('', str(text))).strip()


def human(n):
    n = float(n)
    for u in ['B', 'KB', 'MB', 'GB']:
        if n < 1024 or u == 'GB':
            return f"{n:.0f} {u}" if u == 'B' else f"{n:.1f} {u}"
        n /= 1024


def isnull(v):
    return v is None or v is pd.NA or (isinstance(v, float) and math.isnan(v))


def f_fmt(v):
    if isnull(v) or v == '':
        return '—'
    try:
        return f"{int(round(float(v))):,}"
    except (TypeError, ValueError):
        return str(v)


def f_pct(v):
    return '—' if isnull(v) else f"{100*float(v):.0f}%"


def f_pct1(v):
    return '—' if isnull(v) else f"{100*float(v):.1f}%"


def f_num2(v):
    return '—' if isnull(v) else f"{float(v):.2f}"


def f_numint(v):
    if isnull(v) or v == '':
        return ''
    try:
        return str(int(round(float(v))))
    except (TypeError, ValueError):
        return str(v)


def clean(d):
    """dict with NaN -> None so templates can test truthiness."""
    return {k: (None if isnull(v) else v) for k, v in d.items()}


def write_csv_gz(df, path):
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    with open(path, 'wb') as fh, gzip.GzipFile(filename='', mode='wb', fileobj=fh, mtime=0) as gz:
        gz.write(buf.getvalue().encode('utf-8'))


def dumps(o):
    return json.dumps(o, ensure_ascii=False, separators=(',', ':'), sort_keys=True)


def issue_url(**fields):
    """B4: prefilled GitHub issue-form URL. Field names = ids in .github/ISSUE_TEMPLATE/catalog-finding.yml."""
    q = [('template', ISSUE_TEMPLATE), ('labels', 'finding')]
    title = fields.pop('title', None)
    if title:
        q.append(('title', title[:200]))
    for k in sorted(fields):
        v = fields[k]
        if v is None or v == '':
            continue
        v = str(v)
        if k == 'current_state':
            v = v[:2500]
            while len(quote(v, safe='')) > 4000:  # F18: byte budget BEFORE encoding, never cut inside a %XX escape
                v = v[:-50]
        q.append((k, v))
    url = ISSUE_REPO + '?' + '&'.join(f'{k}={quote(v, safe="")}' for k, v in q)
    assert len(url) <= 6000, 'issue URL over 6 kB'
    return url


def read_base_url(cfg_path):
    """config/site.yaml without a YAML dependency: base_url and placeholder_base_url."""
    txt = Path(cfg_path).read_text(encoding='utf-8') if cfg_path and Path(cfg_path).exists() else ''
    m = re.search(r'^\s*base_url:\s*"?([^"\s#]+)"?', txt, re.M)
    p = re.search(r'^\s*placeholder_base_url:\s*"?([^"\s#]+)"?', txt, re.M)
    return (m.group(1) if m else None), (p.group(1) if p else 'https://USERNAME.github.io/REPOSITORY/')


def read_release_spec(cfg_path):
    """config/releases.yaml — the frozen bitemporal spec shared with src/catalog/release (ids, column names, table list, page paths)."""
    spec = yaml.safe_load(Path(cfg_path).read_text(encoding='utf-8'))
    for k in ('columns', 'files', 'registry_columns', 'site_pages', 'release_id'):
        assert k in spec, f'config/releases.yaml lacks {k}'
    return spec


def read_contribute_spec(cfg_path):
    """config/contribute.yaml — the frozen R2026.2 worklist schema shared with src/catalog/contribute. The generator reads only:
    blocker codes + labels, contribution types + labels, fields + weights + threshold, column lists and the issue_url template."""
    spec = yaml.safe_load(Path(cfg_path).read_text(encoding='utf-8'))
    for k in ('blocker_codes', 'contribution_types', 'fields', 'field_weights', 'missing_threshold', 'worklist_columns', 'fields_columns', 'issue_form', 'files'):
        assert k in spec, f'config/contribute.yaml lacks {k}'
    return spec


def contribute_issue_url(spec, acc, ctype, release_id):
    """Prefilled contribution Issue URL (ids = query keys of catalog-contribution.yml). Same rule as the Data track's build_worklist."""
    f = spec['issue_form']
    title = quote(f['title'].format(study_accession=acc, contribution_type=ctype), safe='')
    return f['url_template'].format(repo=f['repo'], template=f['template'], label=f['label'], title=title, study_accession=acc, contribution_type=ctype, release_id=release_id)


def read_data_repo_id(cfg_path):
    """config/site.yaml github.data_repo_id (GitHub repository id of the data repo; Zenodo badge/latestdoi URLs are built from it)."""
    txt = Path(cfg_path).read_text(encoding='utf-8') if cfg_path and Path(cfg_path).exists() else ''
    m = re.search(r'^\s*data_repo_id:\s*(\d+)', txt, re.M)
    return int(m.group(1)) if m else None


def release_order_key(spec):
    """sort key: historical semver ids first (in spec order), then numbered R<YYYY>.<n> ids by (year, n)."""
    hist = {r: i for i, r in enumerate(spec['release_id']['historical'])}

    def key(rid):
        rid = str(rid)
        if rid in hist:
            return (0, hist[rid], 0)
        m = re.fullmatch(r'R(\d{4})\.(\d+)', rid)
        return (1, int(m.group(1)), int(m.group(2))) if m else (2, 0, 0)
    return key


UPSTREAM_CITATIONS = [  # mandatory upstream citations (methods page carries the same three)
    dict(key='insdc', text='Archive metadata: European Nucleotide Archive / INSDC (ENA, SRA, DDBJ) — archive metadata remains under INSDC terms.', url='https://www.ebi.ac.uk/ena/browser/'),
    dict(key='sandpiper', text='Community profiles: Woodcroft, B. J. et al. Comprehensive taxonomic identification of microbial species in metagenomic data using SingleM and Sandpiper. Nature Biotechnology (2025); bulk snapshot Zenodo record 20419175 (CC-BY).', url='https://doi.org/10.5281/zenodo.20419175'),
    dict(key='cmd', text='Gold evaluation set: Pasolli, E. et al. Accessible, curated metagenomic data through ExperimentHub (curatedMetagenomicData). Nature Methods 14, 1023–1024 (2017).', url='https://doi.org/10.1038/nmeth.4468'),
]


def counts_sorted(series):
    vc = series.value_counts()
    return sorted(((str(k), int(v)) for k, v in vc.items()), key=lambda x: (-x[1], x[0]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--package', required=True)
    ap.add_argument('--out', default='site')
    ap.add_argument('--reports', default=None, help='dir with CATALOG_REPORT.md, EXTRACTION_REPORT.md, field_coverage.png (internal planning documents such as NEXT_STAGE.md / SCALE_UP_PLAN.md are never published — F7)')
    ap.add_argument('--package-zip', default=None, help='path to the whole-package zip to copy into data/package/')
    ap.add_argument('--config', default=str(HERE.parent.parent / 'config' / 'site.yaml'))
    ap.add_argument('--base-url', default=None, help='overrides config/site.yaml site.base_url')
    ap.add_argument('--releases-config', default=str(HERE.parent.parent / 'config' / 'releases.yaml'), help='frozen bitemporal/release spec shared with src/catalog/release')
    ap.add_argument('--contribute-config', default=str(HERE.parent.parent / 'config' / 'contribute.yaml'), help='frozen contribution-worklist spec shared with src/catalog/contribute (R2026.2)')
    ap.add_argument('--allow-placeholder-base-url', action='store_true', help='test builds only')
    ap.add_argument('--build-date', default=None, help='overrides VERSION.json build_date (tests only)')
    ap.add_argument('--max-rows-html', type=int, default=2000)
    ap.add_argument('--show-rows-html', type=int, default=500)
    a = ap.parse_args()
    t0 = time.time()
    pkg, out = Path(a.package), Path(a.out)
    cfg_base, placeholder = read_base_url(a.config)
    base_url = a.base_url or cfg_base or placeholder
    if not base_url.endswith('/'):
        base_url += '/'
    if base_url == placeholder and not a.allow_placeholder_base_url:
        sys.exit(f'refusing to build: base_url is the placeholder {placeholder!r} (A15). Set site.base_url in config/site.yaml or pass --base-url.')
    if out.exists():
        shutil.rmtree(out)
    for d in ['studies', 'cohorts', 'samples', 'fields', 'authors/idx', 'static/vendor', 'docs', 'data/studies', 'data/cohorts', 'data/package', 'releases', 'changes', 'contribute']:
        (out / d).mkdir(parents=True, exist_ok=True)

    # ---------- load ----------
    vj = json.loads((pkg / 'VERSION.json').read_text())
    version = vj['package_version']
    build_date = a.build_date or vj['build_date']
    readme = (pkg / 'README.md').read_text(encoding='utf-8')
    m = re.search(r'data package v(\d+(?:\.\d+)*)', readme)
    readme_version_warning = None
    if not m or m.group(1) != version:
        if m and m.group(1) == vj.get('previous_version'):
            readme_version_warning = f'README heading says v{m.group(1)} while VERSION.json is {version} (package-side defect; site uses VERSION.json)'
            print('WARNING: ' + readme_version_warning, file=sys.stderr)
        else:
            sys.exit(f'README heading version {m.group(1) if m else None!r} != VERSION.json {version!r} (A7)')
    sw = pd.read_parquet(pkg / 'sample_metadata_wide.parquet')
    st = pd.read_parquet(pkg / 'study_metadata_wide.parquet')
    sd = pd.read_parquet(pkg / 'sample_determinations.parquet')
    runs = pd.read_parquet(pkg / 'runs.parquet')
    pb = pd.read_parquet(pkg / 'parent_biosamples.parquet')
    svh = pd.read_parquet(pkg / 'study_verdict_history.parquet')
    vh = pd.read_parquet(pkg / 'value_history.parquet', columns=['sample_key', 'status'])
    coh = pd.read_csv(pkg / 'cohorts.csv')
    spl = pd.read_csv(pkg / 'study_paper_links.csv', dtype={'paper_id': str})
    uni = pd.read_parquet(pkg / 'universe_studies_all.parquet')
    # ---------- releases (R2026.1: config/releases.yaml is the one spec both tracks read) ----------
    rspec = read_release_spec(a.releases_config)
    RA, RR, PA = rspec['columns']['release_added'], rspec['columns']['release_retired'], rspec['columns']['package_added']
    RREASON, RSTAGE = rspec['columns']['retired_reason'], rspec['columns']['retired_change_stage']
    rel_key = release_order_key(rspec)
    reg = pd.read_csv(pkg / rspec['files']['registry'], dtype=str, keep_default_na=False)
    assert list(reg.columns) == list(rspec['registry_columns']), f"releases.csv columns {list(reg.columns)} != spec {rspec['registry_columns']}"
    assert reg.release_id.is_unique and len(reg), 'releases.csv: one row per release id'
    reg = reg.assign(_k=reg.release_id.map(rel_key)).sort_values('_k', kind='mergesort').drop(columns='_k').reset_index(drop=True)
    release_id = vj.get('release_id')
    assert release_id and release_id in set(reg.release_id), f'VERSION.json release_id {release_id!r} must be a releases.csv row'
    assert release_id == reg.release_id.iloc[-1], f'VERSION.json release_id {release_id!r} must be the newest releases.csv row ({reg.release_id.iloc[-1]!r})'
    cur_rel = reg[reg.release_id == release_id].iloc[0].to_dict()
    assert cur_rel['package_version'] == version, f'releases.csv package_version {cur_rel["package_version"]} != VERSION.json {version}'
    assert cur_rel['data_tag'] == vj['release_tag'], 'releases.csv data_tag must equal VERSION.json release_tag'
    sda_path = pkg / rspec['files']['determinations_all']
    sda = pd.read_parquet(sda_path, columns=['study_accession', 'field_name', 'sample_key', RA, RR, RREASON, RSTAGE])
    assert {RA, RR} <= set(sd.columns) and {RA, RR} <= set(uni.columns), 'fact tables lack release columns (package must be >= 1.3.0)'
    assert (sda[RR].isna().sum()) == len(sd), 'sample_determinations_all current rows must equal sample_determinations rows'
    known_ids = set(reg.release_id)
    for df_, nm in ((sd, 'sample_determinations'), (uni, 'universe_studies_all'), (sda, 'sample_determinations_all')):
        bad = set(df_[RA].dropna().astype(str)) | set(df_[RR].dropna().astype(str))
        assert bad <= known_ids, f'{nm}: release ids {sorted(bad - known_ids)[:5]} missing from releases.csv'
    data_repo_id = read_data_repo_id(a.config)
    assert data_repo_id, 'config/site.yaml github.data_repo_id is required (Zenodo badge / latestdoi URLs)'
    notes_by_release = {}
    for r in reg.itertuples(index=False):
        nf = r.notes_file
        if nf and nf.startswith('RELEASE_NOTES_') and (pkg / nf).exists():
            notes_by_release[r.release_id] = (pkg / nf).read_text(encoding='utf-8')
    assert release_id in notes_by_release, f"{rspec['files']['release_notes_pattern'].format(release_id=release_id)} missing from the package"
    uni_all = uni
    uni = uni[uni[RR].isna()].reset_index(drop=True) if RR in uni.columns else uni  # current verdict rows drive every existing page
    hrq = pd.read_csv(pkg / 'human_review_queue.csv')
    # ---------- contribution worklist (R2026.2: config/contribute.yaml is the one spec both tracks read) ----------
    cspec = read_contribute_spec(a.contribute_config)
    wl_path = pkg / cspec['files']['worklist']
    has_contribute = wl_path.exists()
    if rel_key(release_id) >= rel_key(cspec['release_id']):
        assert has_contribute, f"{cspec['files']['worklist']} missing from a package of release {release_id} (>= {cspec['release_id']})"
    wl = wlf = None
    if has_contribute:
        wl = pd.read_csv(wl_path, dtype={'own_data_pmids': str, 'missing_fields': str, 'cohort_id': str}, keep_default_na=True)
        wlf = pd.read_csv(pkg / cspec['files']['worklist_fields'])
        assert list(wl.columns) == list(cspec['worklist_columns']), f"{wl_path.name} columns differ from config/contribute.yaml worklist_columns: {sorted(set(wl.columns) ^ set(cspec['worklist_columns']))}"
        assert list(wlf.columns) == list(cspec['fields_columns']), f"{cspec['files']['worklist_fields']} columns differ from config/contribute.yaml fields_columns"
        assert wl.study_accession.is_unique and (wl['rank'].sort_values().values == range(1, len(wl) + 1)).all(), 'worklist: one row per study, rank 1..n'
        assert set(wl.blocker_code) <= set(cspec['blocker_codes']) and 'complete' not in set(wl.blocker_code), f'worklist blocker codes outside the vocabulary: {sorted(set(wl.blocker_code) - set(cspec["blocker_codes"]))}'
        assert set(wl.contribution_type) <= set(cspec['contribution_types']), 'worklist contribution_type outside the vocabulary'
        assert set(wl.triage_verdict) <= {'include', 'uncertain'}, 'worklist verdicts must be include|uncertain'
        assert (wl.n_missing_fields >= 1).all() and (wl.missing_fields.str.split(';').map(len) == wl.n_missing_fields).all(), 'every worklist study must miss >= 1 field'
        assert set(wlf.study_accession) == set(wl.study_accession), 'worklist_fields must cover exactly the worklist studies'
        _ph = cfg_base if cfg_base else ''
        assert wl.issue_url.str.startswith('https://github.com/').all() and wl.issue_url.str.contains('template=' + cspec['issue_form']['template'], regex=False).all(), 'issue_url must be a prefilled Issue-form URL'
        assert not wl.issue_url.str.contains('USERNAME|REPOSITORY', regex=True).any(), 'issue_url carries a placeholder'
        for r in wl.head(5).itertuples(index=False):
            assert r.issue_url == contribute_issue_url(cspec, r.study_accession, r.contribution_type, r.release_added), f'issue_url of {r.study_accession} differs from the config template'
        _inc_wl = wl[wl.triage_verdict == 'include']
        assert set(_inc_wl.study_accession) <= set(st.study_accession), 'included worklist studies must have a study page'
        # F13-style consistency with the shipped tables: catalog-scope counts of included worklist studies equal study_metadata_wide
        _ncs = st.set_index('study_accession').n_catalog_scope
        _bad = [acc for acc, n in zip(_inc_wl.study_accession, _inc_wl.n_catalog_scope) if int(_ncs.get(acc, -1)) != int(n)]
        assert not _bad, f'F13: worklist n_catalog_scope differs from study_metadata_wide for {_bad[:5]}'
    fcs = pd.read_csv(pkg / 'field_coverage_summary.csv')
    gold = pd.read_csv(pkg / 'extraction_gold_eval_hires.csv').rename(columns={'Unnamed: 0': 'field'})
    tiers = pd.read_csv(pkg / 'confidence_tiers.csv')
    tprec = pd.read_csv(pkg / 'tier_field_precision.csv')
    panels = pd.read_parquet(pkg / 'sandpiper_study_panels.parquet')
    spcov = pd.read_csv(pkg / 'sandpiper_study_coverage.csv')
    spqc = pd.read_csv(pkg / 'sandpiper_study_qc_flags.csv')
    flagdefs = json.loads((pkg / 'sandpiper_flag_definitions.json').read_text())
    flag_table = pd.read_csv(pkg / 'sandpiper_flag_table.csv')  # F10: the single QC-flag vocabulary
    flag_rows = [clean(r) for r in flag_table.sort_values(['level', 'field'], kind='mergesort').to_dict('records')]
    authors = pd.read_parquet(pkg / 'authors.parquet')
    sas = pd.read_csv(pkg / 'study_authors_summary.csv')
    orgs = pd.read_parquet(pkg / 'organisations.parquet')
    orgs = orgs[orgs.display_eligible.fillna(False).astype(bool) & orgs.is_organisation.fillna(False).astype(bool) & (orgs.org_type != 'not_an_organisation')]
    org_display = {acc: '; '.join(dict.fromkeys(sorted(g.organisation.dropna().astype(str)))) for acc, g in orgs.groupby('study_accession')}
    leaks = [v for v in org_display.values() if ORG_LEAK_RE.search(v)] + [v for v in sas.organisations.dropna().astype(str) if ORG_LEAK_RE.search(v)]
    assert not leaks, f'F1/R3-5: organisation strings leak submission ids or e-mail addresses: {leaks[:3]}'
    aidx = json.loads((pkg / 'authors_index.json').read_text())
    dictionary = (pkg / 'DATA_DICTIONARY.md').read_text(encoding='utf-8')
    for df_ in (st, uni, hrq):
        if 'note' in df_.columns:
            df_['note'] = df_['note'].map(strip_frame_tokens)
    assert (sw.sample_unit != 'biosample_pooled').all(), 'B2: parent rows must live in parent_biosamples.parquet'
    assert 'n_sample_rows' in st.columns and 'catalog_scope' in sw.columns, 'package must be >= v1.2.1 (F6/F9 columns)'
    assert sw.sample_key.is_unique
    st = st.sort_values(['n_samples', 'study_accession'], ascending=[False, True]).reset_index(drop=True)
    included = sorted(set(st.study_accession))

    # ---------- stats (all from tables) ----------
    INFANT_SCOPES = ['infant_evidenced', 'study_all_infant']
    infant_scope = sw[sw.body_site_class.isin(['primary', 'unknown'])]
    age_scope_inf = sw[sw.age_scope.isin(INFANT_SCOPES)]
    n_age_in_scope = int((age_scope_inf.age_at_collection_days.notna() & (age_scope_inf.age_at_collection_days <= 1100)).sum())
    fcs = fcs.rename(columns={'field': 'field_name'})
    age_row = fcs[fcs.field_name == 'age_at_collection_days'].iloc[0]
    gold_age = gold[gold.field == 'age_days'].iloc[0]
    age_scope_counts = counts_sorted(sw.age_scope.fillna('unknown'))
    stats = dict(
        n_studies=len(st), n_samples=len(sw), n_runs=int(len(runs)), n_determinations=len(sd), n_biosamples=int((sw.sample_unit == 'biosample').sum()),
        n_run_units=int((sw.sample_unit == 'run').sum()), n_parents=len(pb),
        n_age=int(age_row.n_values_infant_scope_bodysite), pct_age=int(round(100 * float(age_row.coverage_infant_scope_bodysite))),
        n_infant_scope=len(infant_scope), n_age_scope_infant=len(age_scope_inf),
        n_catalog_scope=int(sw.catalog_scope.fillna(False).astype(bool).sum()), n_body_site_excluded=int(age_scope_inf.body_site_class.isin(['excluded', 'linked']).sum()),
        n_age_catalog_scope=int(age_row.n_values_catalog_scope), pct_age_catalog_scope=int(round(100 * float(age_row.coverage_catalog_scope))),
        n_age_in_scope=n_age_in_scope, pct_age_in_scope=int(round(100 * n_age_in_scope / max(1, len(age_scope_inf)))),
        age_scope_counts=age_scope_counts,
        gold_age_precision=f"{float(gold_age.precision):.3f}", gold_n_age=int(gold_age.gold_n),
        n_universe=len(uni), n_excluded=int((uni.catalog_status == 'excluded').sum()),
        n_review=int((uni.catalog_status == 'human_review').sum()),
        n_cohorts=len(coh), n_papers=int(spl.paper_id.nunique()), n_links=len(spl),
        n_adult=int(sw.adult_age_flag.fillna(False).astype(bool).sum()),
        n_profiled=int(sw.sp_profiled.fillna(False).astype(bool).sum()), n_runs_profiled=int(spcov.n_runs_profiled.sum()),
        # F6: ONE definition everywhere — a study is 'profiled' when >= 1 of its sample rows is profiled; own-run and panel counts are reported alongside
        n_studies_profiled=int(sw.loc[sw.sp_profiled.fillna(False).astype(bool), 'study_accession'].nunique()),
        n_studies_own_runs_profiled=int((spcov.n_runs_profiled > 0).sum()), n_studies_with_panel=int(panels.study_accession.nunique()),
        gold_recall_sentence=GOLD_RECALL_SENTENCE,
        n_authors=int(authors.author_key.nunique()), n_author_rows=len(authors), n_studies_with_author=int(sas.has_any_author.astype(bool).sum()),
        n_included_no_author=int(((sas.catalog_status == 'included') & ~sas.has_any_author.astype(bool)).sum()),
        n_history=len(svh), n_value_history=int(vh.shape[0]), n_mixed=int(st.mixed_age_deposit.fillna(False).astype(bool).sum()),
        taxonomy=f"{panels.taxonomy_db.iloc[0]} {panels.taxonomy_version.iloc[0]}" if len(panels) else 'GTDB',
    )
    stats['pct_profiled'] = int(round(100 * stats['n_profiled'] / max(1, stats['n_samples'])))
    stats['n_contribute'] = int(len(wl)) if has_contribute else 0
    stats['n_contribute_samples'] = int(wl.n_samples.sum()) if has_contribute else 0
    stats['has_contribute'] = has_contribute
    assert stats['n_biosamples'] + stats['n_run_units'] == stats['n_samples'], 'F4: BioSample units + run units must equal the sample count'
    assert stats['n_studies_profiled'] == int((spcov.n_samples_profiled > 0).sum()) == int((st.sp_n_samples_profiled.fillna(0) > 0).sum()), 'F6: profiled-study definition disagrees between tables'
    assert stats['n_catalog_scope'] == stats['n_age_scope_infant'] - stats['n_body_site_excluded'], 'F9: catalog_scope must equal age-scope minus body-site excluded/linked'
    gen_sha = vj.get('generator_git_sha', 'nogit')
    doi = cur_rel.get('doi') or ''
    site = dict(title='Infant Gut Shotgun-Metagenome Catalog', version=version, release_tag=vj['release_tag'], build_date=build_date,
                sha8=gen_sha[:8], base_url=base_url, issue_repo=ISSUE_REPO,
                release_id=release_id, previous_release_id=vj.get('previous_release_id'), release_date=cur_rel['release_date'], doi=doi,
                data_release_url=rspec['site_pages']['data_release_url'].format(data_tag=cur_rel['data_tag']) if cur_rel['data_tag'] else None,
                zenodo_badge=f'https://zenodo.org/badge/{data_repo_id}.svg', zenodo_latest=f'https://zenodo.org/badge/latestdoi/{data_repo_id}', data_repo_id=data_repo_id,
                upstream=UPSTREAM_CITATIONS, releases_page=rspec['site_pages']['releases_index'], changes_page=rspec['site_pages']['changes_index'],
                description='Curated, evidence-linked catalog of public shotgun-metagenome studies of the human infant gut with per-sample metadata and Sandpiper community profiles.',
                citation=f'Infant Gut Shotgun-Metagenome Catalog, release {release_id} (data package {version}), OlmLab, {cur_rel["release_date"]}.' + (f' doi:{doi}' if doi else ''),
                sri=json.loads((HERE / 'static' / 'vendor' / 'SRI.json').read_text()), has_contribute=has_contribute, contribute_page='contribute/index.html')

    env = Environment(loader=FileSystemLoader(HERE / 'templates'), autoescape=select_autoescape(['html']))
    env.filters.update(fmt=f_fmt, pct=f_pct, pct1=f_pct1, num2=f_num2, numint=f_numint)
    env.globals.update(site=site)
    written = []

    def render(tpl, path, root, nav=None, crumbs=None, **ctx):
        html = env.get_template(tpl).render(root=root, nav=nav, crumbs=crumbs, page_path=path, **ctx)
        (out / path).write_text(html, encoding='utf-8')
        written.append(path)

    # ---------- static ----------
    for f in sorted((HERE / 'static').rglob('*')):
        if f.is_file():
            rel = f.relative_to(HERE / 'static')
            (out / 'static' / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f, out / 'static' / rel)
    (out / '.nojekyll').write_text('')
    rep = Path(a.reports) if a.reports else None
    if rep and (rep / 'field_coverage.png').exists():
        shutil.copyfile(rep / 'field_coverage.png', out / 'static' / 'field_coverage.png')

    # ---------- data files ----------
    IN_DATA = ['sample_metadata_wide.parquet', 'sample_determinations.parquet', 'value_history.parquet', 'sandpiper_top_genera.parquet', rspec['files']['determinations_all']]
    for name in IN_DATA:
        shutil.copyfile(pkg / name, out / 'data' / name)
    pkg_files = []
    for f in sorted(pkg.iterdir()):
        if not f.is_file() or f.name == 'build_counts.json':
            continue
        if f.name not in IN_DATA:
            shutil.copyfile(f, out / 'data' / 'package' / f.name)
        meta = vj['tables'].get(f.name, {})
        pkg_files.append(dict(name=f.name, size=human(f.stat().st_size), bytes=f.stat().st_size, rows=meta.get('rows'),
                              sha256=meta.get('sha256', ''), href=('data/' if f.name in IN_DATA else 'data/package/') + f.name,
                              desc=FILE_DESC.get(f.name, ''), sandpiper=f.name.startswith('sandpiper') or f.name == 'SANDPIPER_REPORT.md'))
    zip_name, zip_size = None, None
    if a.package_zip:
        zip_name = f'data_package_v{version}.zip'
        shutil.copyfile(a.package_zip, out / 'data' / 'package' / zip_name)
        zip_size = human(Path(a.package_zip).stat().st_size)

    sw_sorted = sw.sort_values(['study_accession', 'subject_key', 't_index', 'sample_key'], na_position='last', kind='mergesort')
    study_dl = {}
    for acc, g in sw_sorted.groupby('study_accession', sort=True):
        write_csv_gz(g, out / 'data' / 'studies' / f'{acc}.csv.gz')
        g.to_parquet(out / 'data' / 'studies' / f'{acc}.parquet', index=False)
        study_dl[acc] = dict(csv_size=human((out / 'data' / 'studies' / f'{acc}.csv.gz').stat().st_size),
                             parquet_size=human((out / 'data' / 'studies' / f'{acc}.parquet').stat().st_size))
    for acc in included:
        g = sd[sd.study_accession == acc].sort_values(['sample_key', 'field_name'], kind='mergesort')
        p = out / 'data' / 'studies' / f'{acc}_determinations.csv.gz'
        write_csv_gz(g, p)
        study_dl.setdefault(acc, dict(csv_size='0 B', parquet_size='0 B'))
        study_dl[acc].update(det_size=human(p.stat().st_size), det_rows=len(g))
    cohort_dl = {}
    coh_members = {r.cohort_id: [x for x in str(r.included_study_accessions or '').split('|') if x and x != 'nan']
                   for r in coh.itertuples(index=False)}
    for cid in sorted(coh_members):
        accs = coh_members[cid]
        if len(accs) < 2:
            continue
        g = sw_sorted[sw_sorted.study_accession.isin(accs)]
        write_csv_gz(g, out / 'data' / 'cohorts' / f'{cid}.csv.gz')
        g.to_parquet(out / 'data' / 'cohorts' / f'{cid}.parquet', index=False)
        cohort_dl[cid] = dict(csv_size=human((out / 'data' / 'cohorts' / f'{cid}.csv.gz').stat().st_size),
                              parquet_size=human((out / 'data' / 'cohorts' / f'{cid}.parquet').stat().st_size))
    print(f'[{time.time()-t0:.0f}s] data files written', file=sys.stderr)

    # ---------- docs (markdown -> html) ----------
    def md_to_html(text):
        html = markdown.markdown(text, extensions=['tables', 'fenced_code', 'toc'])
        return re.sub(r'<a href="([^"]+)">', lambda m: m.group(0) if m.group(1).startswith(('http', '#')) else '<a>', html)
    docs = [('README.md', readme, 'README'), ('DATA_DICTIONARY.md', dictionary, 'Data dictionary'), ('CHANGELOG.md', (pkg / 'CHANGELOG.md').read_text(encoding='utf-8'), 'Changelog')]
    for name, title in [('SANDPIPER_REPORT.md', 'Sandpiper report'), ('AUTHORS_REPORT.md', 'Authors report'), ('DATA_MODEL_FIX_REPORT.md', 'Data-model fix report')]:
        if (pkg / name).exists():
            docs.append((name, (pkg / name).read_text(encoding='utf-8'), title))
    for name, title in PUBLIC_REPORT_DOCS:
        if rep and (rep / name).exists() and name not in [d[0] for d in docs]:
            docs.append((name, (rep / name).read_text(encoding='utf-8'), title))
    doc_list = []
    for name, text, title in docs:
        (out / 'docs' / name).write_text(text, encoding='utf-8')
        render('doc.html', f'docs/{name[:-3]}.html', '../', nav='methods', doc_title=title, md_name=name, body=md_to_html(text),
               crumbs=[dict(label='Home', href='../index.html'), dict(label='Methods', href='../methods.html'), dict(label=title)])
        doc_list.append(dict(name=name, title=title, href=f'docs/{name[:-3]}.html'))

    # ---------- per-study helpers ----------
    papers_by_study = {}
    for r in spl.sort_values(['study_accession', 'paper_id']).itertuples(index=False):
        papers_by_study.setdefault(r.study_accession, []).append(dict(
            pmid=None if isnull(r.pmid) else int(r.pmid), pmcid=None if isnull(r.pmcid) else r.pmcid,
            doi=None if isnull(r.doi) else r.doi, title=None if isnull(r.title) else r.title))
    parents_by_study = {acc: [clean(r) for r in g.sort_values('sample_key').to_dict('records')] for acc, g in pb.groupby('study_accession')}
    hist_by_study = {}
    # R3-6: order by the stage ontology (stage_rank), not by artifact date; consolidated rows collapse to one 'final' line
    svh_live = svh[~svh.is_consolidated.fillna(False).astype(bool)]
    svh_final = svh[svh.is_consolidated.fillna(False).astype(bool) & (svh.consolidated_kind == 'final')]
    _hid = svh.is_consolidated.fillna(False).astype(bool) & (svh.consolidated_kind != 'final')
    n_consolidated_hidden = svh.loc[_hid].groupby('study_accession').size().astype(int).to_dict()
    def hist_row(r, order):
        try:
            ev = json.loads(r.evidence) if isinstance(r.evidence, str) and r.evidence.startswith('[') else []
            quotes = ' · '.join(f"“{e.get('quote','')}” ({e.get('source','')})" for e in ev if isinstance(e, dict))[:400]
        except ValueError:
            quotes = str(r.evidence)[:200]
        vnorm = None if isnull(r.verdict_norm) else str(r.verdict_norm)
        vnote = None if isnull(r.verdict_norm_note) else str(r.verdict_norm_note)
        return dict(order=order, stage=r.stage if not isnull(r.stage) else '', level=r.stage_level, verdict=vnorm or '—', verdict_raw='' if isnull(r.verdict) else str(r.verdict), verdict_note=vnote,
                    conf=None if isnull(r.confidence) else round(float(r.confidence), 2), model=r.model or '', reason=None if isnull(r.reason_code) else r.reason_code,
                    quotes=quotes, table=r.stage_table, final=bool(r.is_final), consolidated=bool(r.is_consolidated),
                    replicate=None if isnull(r.replicate) else int(r.replicate), date=str(r.date)[:10] if not isnull(r.date) else '')
    for acc, g in svh_live.groupby('study_accession'):
        rows = []
        for i, r in enumerate(g.sort_values(['stage_rank', 'stage', 'replicate', 'date'], kind='mergesort', na_position='last').itertuples(index=False), start=1):
            rows.append(hist_row(r, i))
        hist_by_study[acc] = rows
    for acc, g in svh_final.groupby('study_accession'):
        r = g.sort_values(['stage_rank', 'date'], kind='mergesort', na_position='last').iloc[-1]
        row = hist_row(r, len(hist_by_study.get(acc, [])) + 1)
        row['final'] = True
        hist_by_study.setdefault(acc, []).append(row)
    if len(svh):
        _first = svh_live[svh_live.stage_level == 'screen'].groupby('study_accession').stage_rank.min()
        _others = svh_live[svh_live.stage_level != 'screen'].groupby('study_accession').stage_rank.min()
        _both = _first.index.intersection(_others.index)
        assert (_first.loc[_both] < _others.loc[_both]).all(), 'R3-6: screen stage must precede every other stage'
    # R2026.1: verdict timeline across releases — every verdict row of the study (current + retired) from universe_studies_all
    def _quote(ev):
        try:
            e = json.loads(ev) if isinstance(ev, str) and ev.startswith('[') else []
            return ' · '.join(f"“{x.get('quote','')}” ({x.get('source','')})" for x in e if isinstance(x, dict))[:300]
        except ValueError:
            return str(ev)[:200]
    timeline_by_study = {}
    _tl = uni_all.assign(_k=uni_all[RA].astype(str).map(rel_key))
    for acc, g in _tl.groupby('study_accession'):
        rows = []
        for r in g.sort_values(['_k', RA], kind='mergesort').itertuples(index=False):
            d = r._asdict()
            rows.append(dict(release_added=d[RA], release_retired=None if isnull(d[RR]) else d[RR], package_added=None if isnull(d.get(PA)) else d.get(PA),
                             verdict='' if isnull(d['triage_verdict']) else str(d['triage_verdict']), status='' if isnull(d['catalog_status']) else str(d['catalog_status']),
                             conf=None if isnull(d['confidence']) else round(float(d['confidence']), 2), stage='' if isnull(d['decision_stage']) else str(d['decision_stage']),
                             reason='' if isnull(d['reason_code']) else str(d['reason_code']), quote=_quote(d['evidence']), current=isnull(d[RR])))
        timeline_by_study[acc] = rows
    panel_by_study = {}
    PANEL_SCOPE_TEXT = {  # F9: distinguish 'no catalog-scope samples' from 'no profiles' (labels from sandpiper_study_panel_status.csv)
        'no_profiled_samples': 'No run of this study is in the Sandpiper snapshot, so no community profile exists',
        'fallback:no_catalog_scope_samples': 'This study has no catalog-scope samples (age-scope infant AND gut/unknown body site), so no infant-gut composition panel is shown',
        'fallback:no_age_evidenced_profiled_samples': 'None of the profiled samples has age-scope infant evidence, so no infant-gut composition panel is shown',
        'fallback:all_age_evidenced_profiled_samples_low_depth': 'Every profiled catalog-scope sample is low depth (root coverage < 2×), so no panel is shown',
    }
    for acc, g in panels.groupby('study_accession'):
        d = {}
        r0 = g.iloc[0]
        for rank in ['phylum', 'genus']:
            gg = g[g['rank'] == rank].sort_values(['rank_order', 'taxon'], kind='mergesort')
            segs, left, ci = [], 0.0, 0
            for r in gg.itertuples(index=False):
                w = 100 * float(r.mean_rel_abundance)
                unassigned = str(r.taxon).startswith('unassigned')
                color = UNASSIGNED_COLOR if unassigned else TAXON_PALETTE[ci % len(TAXON_PALETTE)]
                if not unassigned:
                    ci += 1
                segs.append(dict(taxon=r.taxon, label=re.sub(r'^[a-z]__', '', r.taxon), pct=round(w, 1), left=round(left, 2), w=round(w, 2), color=color))
                left += w
            other = max(0.0, 100 - left)
            if other > 0.05:
                segs.append(dict(taxon='other', label='other named taxa', pct=round(other, 1), left=round(left, 2), w=round(other, 2), color='#FFFFFF'))
            n = int(gg.n_samples_panel.iloc[0]) if len(gg) else int(r0.n_samples_panel)
            assert n == int(r0.n_samples_panel), f'F13: panel n differs between ranks for {acc}'
            d[rank] = dict(segs=segs, n=n)
        d.update(n=int(r0.n_samples_panel), n_samples_study=int(r0.n_samples_study), n_catalog_scope=int(r0.n_catalog_scope), n_profiled=int(r0.n_profiled),
                 n_profiled_catalog_scope=int(r0.n_profiled_catalog_scope), n_age_infant=int(r0.n_profiled_age_infant), n_age_adult=int(r0.n_profiled_age_adult),
                 n_age_unknown=int(r0.n_profiled_age_unknown_or_other), n_low_depth=int(r0.n_low_depth_excluded_from_panel), frac=float(r0.frac_samples_profiled),
                 scope=str(r0.panel_scope), definition=str(r0.panel_definition), taxonomy=f"{r0.taxonomy_db} {r0.taxonomy_version}")
        panel_by_study[acc] = d
    pstatus = pd.read_csv(pkg / 'sandpiper_study_panel_status.csv')
    pstatus_by = {r['study_accession']: clean(r) for r in pstatus.to_dict('records')}
    n_by_study_rows = sw.groupby('study_accession').size()
    for acc, ps in pstatus_by.items():
        ps['scope_text'] = PANEL_SCOPE_TEXT.get(ps.get('panel_scope'), '' if acc in panel_by_study else f"No panel ({ps.get('panel_scope')})")
        if ps.get('panel_scope') == 'fallback:no_catalog_scope_samples' and (ps.get('n_profiled_age_infant') or 0) > 0:
            ps['scope_text'] += f"; its {int(ps['n_profiled_age_infant']):,} profiled infant-age samples are body-site excluded/linked (see body-site classes above)"
        if acc in panel_by_study:
            assert panel_by_study[acc]['n'] == int(ps['n_samples_panel']), f'F13: panel n != panel_status n for {acc}'
        # F13: panel denominators must match the shipped wide table
        assert int(ps['n_samples_study']) == int(n_by_study_rows.get(acc, 0)), f'F13: n_samples_study != wide-table rows for {acc}'
        _g = sw[sw.study_accession == acc]
        _n_panel = int((_g.catalog_scope.fillna(False).astype(bool) & _g.sp_profiled.fillna(False).astype(bool) & ~_g.sp_low_depth.fillna(False).astype(bool)).sum())
        assert _n_panel == int(ps['n_samples_panel']), f'F13: recomputed panel n {_n_panel} != {ps["n_samples_panel"]} for {acc}'
    assert set(panel_by_study) <= set(pstatus_by), 'F13: every panel needs a status row'
    spcov_by = {r['study_accession']: clean(r) for r in spcov.to_dict('records')}
    spqc_by = {r['study_accession']: clean(r) for r in spqc.to_dict('records')}
    authors_by_study = {}
    for acc, g in authors.groupby('study_accession'):
        g = g.sort_values(['pmid', 'position'], kind='mergesort')
        seen, lst = set(), []
        for r in g.itertuples(index=False):
            if r.author_display in seen:
                continue
            seen.add(r.author_display)
            lst.append(dict(name=r.author_display, key=r.author_key, first=bool(r.is_first), last=bool(r.is_last)))
        authors_by_study[acc] = lst
    sas_by = {r['study_accession']: clean(r) for r in sas.to_dict('records')}
    for acc, d in sas_by.items():
        d['organisations'] = org_display.get(acc, '')  # F1/R3-5: only org_type-displayable organisations are ever rendered
    vh_by_sample = vh.groupby('sample_key').size()

    # ---------- contribute: per-study 'Help complete this study' panels ----------
    CFIELDS = cspec['fields']                      # short key -> package field name
    CSHORT = {v: k for k, v in CFIELDS.items()}
    # short UI labels (merged spec): blocker_labels / contribution_type_labels; fall back to the code->definition maps
    BLABEL, TLABEL = cspec.get('blocker_labels', cspec['blocker_codes']), cspec.get('contribution_type_labels', cspec['contribution_types'])
    help_by_study, wl_rows = {}, []
    if has_contribute:
        tiers_by = {(r.study_accession, r.field): r for r in wlf.itertuples(index=False)}
        for r in wl.sort_values('rank', kind='mergesort').to_dict('records'):
            r = clean(r)
            acc = r['study_accession']
            missing = [f for f in str(r['missing_fields']).split(';') if f]
            chips = []
            for k, f in CFIELDS.items():
                cov = float(r.get(f'coverage_{k}') or 0)
                chips.append(dict(field=f, short=k, label=LABELS.get(f, f), cov=cov, pct=f'{100*cov:.0f}%', tier=str(r.get(f'best_tier_{k}') or 'R0'), missing=f in missing))
            pmids = [p for p in str(r.get('own_data_pmids') or '').split(';') if p and p != 'nan']
            row = dict(r, chips=chips, pmids=pmids, missing=missing, blocker_label=BLABEL.get(r['blocker_code'], r['blocker_code']), type_label=TLABEL.get(r['contribution_type'], r['contribution_type']),
                       has_page=acc in set(included), cohort_has_page=bool(r.get('cohort_id')) and r.get('cohort_id') in set(coh.cohort_id.astype(str)), controlled_access=bool(r.get('controlled_access')) if r.get('controlled_access') not in (None, '', 'False', False) else False,
                       k=f"{acc} {r.get('study_title') or ''} {r.get('cohort_name') or ''} {r['blocker_code']}".lower())
            wl_rows.append(row)
            help_by_study[acc] = row
    # ---------- studies ----------
    studies = [clean(r) for r in st.to_dict('records')]
    render('studies_index.html', 'studies/index.html', '../', nav='studies', use_datatables=True, studies=studies,
           crumbs=[dict(label='Home', href='../index.html'), dict(label='Studies')])
    sw_by_study = {acc: g for acc, g in sw_sorted.groupby('study_accession', sort=True)}
    SAMPLE_COLS = ['sample_key', 'sample_unit', 'biosample_accession', 'run_accession', 'ena_sample_url', 'sandpiper_url', 'sp_profiled', 'sp_top_genus',
                   'sp_ra_g_Bifidobacterium', 'age_at_collection_days', 'age_scope', 'delivery_mode', 'feeding_mode', 'preterm_status', 'antibiotic_exposure', 'sex',
                   'subject_key', 't_index', 'role', 'n_runs']
    for s in studies:
        acc = s['study_accession']
        g = sw_by_study.get(acc, sw.iloc[0:0])
        n_total = len(g)
        shown = g if n_total <= a.max_rows_html else g.head(a.show_rows_html)
        try:
            evidence = json.loads(s['evidence']) if s.get('evidence') else []
            if not isinstance(evidence, list):
                evidence = []
        except (ValueError, TypeError):
            evidence = []
        cov = [dict(field=f, label=LABELS[f], frac=float(s.get(f'cov_{f}') or 0)) for f in COV_FIELDS]
        recov = [(k.replace('recov_', ''), s[k] or 'R0') for k in ['recov_age', 'recov_delivery', 'recov_feeding', 'recov_preterm', 'recov_antibiotics', 'recov_probiotic']]
        roles = counts_sorted(g.role.fillna('unknown'))
        sites = counts_sorted(g.body_site_class.fillna('unknown'))
        ages = counts_sorted(g.age_scope.fillna('unknown'))
        ev_txt = '; '.join(f"“{e.get('quote','')}” ({e.get('source','')})" for e in evidence if isinstance(e, dict))[:600]
        flag = issue_url(title=f'[finding] {acc}: verdict', identifier=acc, finding_type='wrong_verdict', action='study_verdict',
                         current_state=f"verdict={s.get('triage_verdict')} · status={s.get('catalog_status')} · stage={s.get('decision_stage')} · confidence={f_num2(s.get('confidence'))} · evidence: {ev_txt}",
                         evidence_source='external_curation.human', release_tag=f"{vj['release_tag']} · studies/{acc}.html")
        confirm = issue_url(title=f'[confirmed] {acc}: verdict', identifier=acc, finding_type='confirmed_correct', action='confirm',
                            current_state=f"verdict={s.get('triage_verdict')} · status={s.get('catalog_status')} · stage={s.get('decision_stage')} · confidence={f_num2(s.get('confidence'))}",
                            proposed_change='none — confirmed correct', evidence_source='external_curation.human', release_tag=f"{vj['release_tag']} · studies/{acc}.html")
        render('study.html', f'studies/{acc}.html', '../', nav='studies', use_datatables=True, s=s,
               papers=papers_by_study.get(acc, []), evidence=evidence, cov=cov, recov=recov, roles=roles, sites=sites, ages=ages,
               parents=parents_by_study.get(acc, []), history=hist_by_study.get(acc, []), timeline=timeline_by_study.get(acc, []), n_consolidated_hidden=n_consolidated_hidden.get(acc, 0), panel=panel_by_study.get(acc), pstatus=pstatus_by.get(acc, {}), spcov=spcov_by.get(acc, {}), spqc=spqc_by.get(acc, {}),
               study_authors=authors_by_study.get(acc, []), sas=sas_by.get(acc, {}), flag_url=flag, confirm_url=confirm, help=help_by_study.get(acc), stats_n_contribute=stats['n_contribute'],
               samples=[clean(r) for r in shown[SAMPLE_COLS].to_dict('records')],
               n_total=n_total, n_shown=len(shown), dl=study_dl[acc],
               crumbs=[dict(label='Home', href='../index.html'), dict(label='Studies', href='index.html'), dict(label=acc)])
    print(f'[{time.time()-t0:.0f}s] {len(studies)} study pages', file=sys.stderr)

    # ---------- cohorts ----------
    uni_by_acc = uni.set_index('study_accession')
    papers_by_id = {}
    for r in spl.sort_values(['paper_id', 'study_accession']).itertuples(index=False):
        d = papers_by_id.setdefault(str(r.paper_id), dict(pmid=str(r.paper_id), pmcid=None, doi=None, title=None, studies=[]))
        d['pmcid'] = d['pmcid'] or (None if isnull(r.pmcid) else r.pmcid)
        d['doi'] = d['doi'] or (None if isnull(r.doi) else r.doi)
        d['title'] = d['title'] or (None if isnull(r.title) else r.title)
        if r.study_accession in included and r.study_accession not in d['studies']:
            d['studies'].append(r.study_accession)
    n_by_study = sw.study_accession.value_counts().to_dict()
    cohorts = []
    for r in coh.to_dict('records'):
        c = clean(r)
        c['n_samples_in_catalog'] = int(sum(n_by_study.get(acc, 0) for acc in coh_members.get(c['cohort_id'], [])))
        c['included_list'] = coh_members.get(c['cohort_id'], [])
        if not isnull(c.get('index_publication_pmid')):
            c['index_publication_pmid'] = int(c['index_publication_pmid'])
        cohorts.append(c)
    cohorts.sort(key=lambda c: (-c['n_samples_in_catalog'], c['cohort_id']))
    render('cohorts_index.html', 'cohorts/index.html', '../', nav='cohorts', use_datatables=True, cohorts=cohorts,
           crumbs=[dict(label='Home', href='../index.html'), dict(label='Cohorts')])
    for c in cohorts:
        cid = c['cohort_id']
        members = []
        for acc in [x for x in str(c.get('study_accessions') or '').split('|') if x]:
            u = uni_by_acc.loc[acc] if acc in uni_by_acc.index else None
            members.append(dict(acc=acc, included=acc in included,
                                title=None if u is None or isnull(u.study_title) else u.study_title,
                                n_samples=None if u is None else u.n_samples,
                                status=(u.catalog_status if u is not None else 'not_in_universe')))
        members.sort(key=lambda m: (not m['included'], m['acc']))
        papers = [papers_by_id.get(pid, dict(pmid=pid, pmcid=None, doi=None, title=None, studies=[])) for pid in str(c.get('paper_ids') or '').split('|') if pid]
        try:
            evidence = json.loads(c['evidence']) if c.get('evidence') else {}
            evidence = {k: v for k, v in sorted(evidence.items()) if isinstance(v, dict) and v.get('quote')} if isinstance(evidence, dict) else {}
        except (ValueError, TypeError):
            evidence = {}
        flag = issue_url(title=f'[finding] {cid}: cohort', identifier=cid, finding_type='other', action='study_note',
                         current_state=f"cohort={c.get('cohort_name')} · decision={c.get('decision')} ({f_num2(c.get('confidence'))}) · studies={c.get('study_accessions')} · unique_infants_est={c.get('unique_infants_est')} ({c.get('unique_infants_outcome')})",
                         evidence_source='external_curation.human', release_tag=f"{vj['release_tag']} · cohorts/{cid}.html")
        confirm = issue_url(title=f'[confirmed] {cid}: cohort', identifier=cid, finding_type='confirmed_correct', action='confirm', proposed_change='none — confirmed correct',
                            current_state=f"cohort={c.get('cohort_name')} · decision={c.get('decision')} · studies={c.get('study_accessions')}", evidence_source='external_curation.human',
                            release_tag=f"{vj['release_tag']} · cohorts/{cid}.html")
        render('cohort.html', f'cohorts/{cid}.html', '../', nav='cohorts', c=c, members=members, papers=papers, evidence=evidence,
               n_samples=c['n_samples_in_catalog'], dl=cohort_dl.get(cid, {}), flag_url=flag, confirm_url=confirm,
               crumbs=[dict(label='Home', href='../index.html'), dict(label='Cohorts', href='index.html'), dict(label=c['cohort_name'])])
    print(f'[{time.time()-t0:.0f}s] {len(cohorts)} cohort pages', file=sys.stderr)

    # ---------- explorer ----------
    def distinct(col):
        return sorted(str(v) for v in sw[col].dropna().unique().tolist() if v != '')
    catfields = [dict(name=f, label=LABELS[f], opts=distinct(f)) for f in CAT_FIELDS]
    coh_opts = [dict(cohort_id=c['cohort_id'], cohort_name=c['cohort_name'], n=c['n_samples_in_catalog']) for c in cohorts if c['n_samples_in_catalog']]
    render('explorer.html', 'samples/index.html', '../', nav='samples', studies=studies, cohorts=coh_opts,
           site_classes=distinct('body_site_class'), roles=distinct('role'), countries=distinct('country'), age_scopes=distinct('age_scope'),
           catfields=catfields, field_names=FIELDS, n_samples=len(sw), n_cols=int(sw.shape[1]),
           parquet_size=human((pkg / 'sample_metadata_wide.parquet').stat().st_size),
           topgen_size=human((pkg / 'sandpiper_top_genera.parquet').stat().st_size), vh_size=human((pkg / 'value_history.parquet').stat().st_size),
           sda_name=rspec['files']['determinations_all'], sda_size=human(sda_path.stat().st_size), release_cols=dict(added=RA, retired=RR, reason=RREASON, stage=RSTAGE),
           issue_template=ISSUE_TEMPLATE, crumbs=[dict(label='Home', href='../index.html'), dict(label='Sample explorer')])

    # ---------- fields ----------
    vocab = {}
    in_vocab = False
    for line in dictionary.splitlines():
        if line.startswith('## Field vocabularies'):
            in_vocab = True
            continue
        if in_vocab and line.startswith('## '):
            in_vocab = False
        if in_vocab and line.startswith('| `'):
            cells = [c.strip() for c in line.strip('|').split('|')]
            name = cells[0].strip('`').strip()
            vocab[name] = ' | '.join(c.strip() for c in cells[1:]).replace('` ', '').strip()
    scope_cols = [f'{f}__scope' for f in COV_FIELDS if f'{f}__scope' in sw.columns]
    fields = []
    route_by_field = sd[sd.sample_key.isin(set(infant_scope.sample_key))].groupby(['field_name', 'route']).size()  # F16: same scope as the Samples column
    for r in fcs.sort_values('field_name').to_dict('records'):
        f = r['field_name']
        if f not in sw.columns:
            continue
        nR = {i: int(route_by_field.get((f, f'R{i}'), 0)) for i in range(1, 5)}
        tot = max(1, sum(nR.values()))
        left, segs = 0.0, []
        for i in range(1, 5):
            w = 100 * nR[i] / tot
            segs.append(dict(r=f'R{i}', left=round(left, 2), w=round(w, 2), n=nR[i]))
            left += w
        has_bs = infant_scope[f].notna()
        n_st = int(infant_scope.loc[has_bs, 'study_accession'].nunique())
        fields.append(dict(name=f, label=LABELS.get(f, f), vocab=vocab.get(f, ''), caveat=FIELD_CAVEATS.get(f, ''), samples=int(r['n_values_infant_scope_bodysite']),
                           frac=float(r['coverage_infant_scope_bodysite']), studies=n_st, frac_studies=n_st / max(1, len(st)),
                           n_age_scope=int(r['n_values_age_scope_infant']), frac_age_scope=float(r['coverage_age_scope_infant']),
                           n_R1=nR[1], n_R2=nR[2], n_R3=nR[3], n_R4=nR[4], route_segs=segs,
                           scopes=counts_sorted(sw.loc[sw[f].notna(), f'{f}__scope'].fillna('unknown')) if f'{f}__scope' in sw.columns else []))
    fields.sort(key=lambda f: (-f['samples'], f['name']))
    extra = []
    for f in ['sex', 'timepoint_label', 'subject_id']:
        has = infant_scope[f].notna()
        rc = sd.loc[(sd.field_name == f) & sd.sample_key.isin(set(infant_scope.sample_key)), 'route'].value_counts()
        extra.append(dict(name=f, label=LABELS.get(f, f), vocab=vocab.get(f, ''), caveat=FIELD_CAVEATS.get(f, ''), samples=int(has.sum()), frac=float(has.mean()),
                          studies=int(infant_scope.loc[has, 'study_accession'].nunique()),
                          n_R1=int(rc.get('R1', 0)), n_R2=int(rc.get('R2', 0)), n_R3=int(rc.get('R3', 0)), n_R4=int(rc.get('R4', 0))))
    tier_rows = [clean(r) for r in tiers.sort_values(['route', 'determined_by', 'scope'], kind='mergesort').to_dict('records')]
    prec = tprec[(tprec.gold_set == 'hires') & (tprec.route != 'ALL')].sort_values(['field', 'route', 'confidence_tier'], kind='mergesort')
    prec_rows = [clean(r) for r in prec.to_dict('records')]
    prec_all = [clean(r) for r in tprec[(tprec.gold_set == 'hires') & (tprec.route == 'ALL')].sort_values('field').to_dict('records')]
    conf_para = ''
    if '## Confidence (v1.2 clarification)' in dictionary:
        conf_para = dictionary.split('## Confidence (v1.2 clarification)')[1].split('\n## ')[0].strip()
    render('fields.html', 'fields/index.html', '../', nav='fields', fields=fields, extra=extra, dictionary_html=md_to_html(dictionary),
           tiers=tier_rows, prec=prec_rows, prec_all=prec_all, conf_para_html=md_to_html(conf_para), stats=stats, scope_cols=scope_cols, flag_rows=flag_rows,
           crumbs=[dict(label='Home', href='../index.html'), dict(label='Fields')])

    # ---------- universe (with authors/organisations) ----------
    status_counts = counts_sorted(uni.catalog_status)
    reason_counts = counts_sorted(uni.reason_code.dropna())
    uidx = []
    for r in uni.sort_values('study_accession').itertuples(index=False):
        au = sas_by.get(r.study_accession, {})
        uidx.append(dict(a=r.study_accession, t='' if isnull(r.study_title) else r.study_title, s=r.catalog_status,
                         r='' if isnull(r.reason_code) else r.reason_code, n=None if isnull(r.n_samples) else int(r.n_samples),
                         k=None if isnull(r.n_runs) else int(r.n_runs), p='' if isnull(r.first_public_min) else str(r.first_public_min),
                         g='' if isnull(r.decision_stage) else r.decision_stage, c=None if isnull(r.confidence) else round(float(r.confidence), 2),
                         fa=au.get('first_author') or '', na=int(au.get('n_authors') or 0), o=(au.get('organisations') or '')[:200]))
    (out / 'data' / 'universe_index.json').write_text(dumps(uidx), encoding='utf-8')
    render('universe.html', 'universe.html', '', nav='universe', use_datatables=True, n_total=len(uni), status_counts=status_counts,
           reason_counts=reason_counts, review=[clean(r) for r in hrq.sort_values('study_accession').to_dict('records')], stats=stats,
           crumbs=[dict(label='Home', href='index.html'), dict(label='Universe')])

    # ---------- authors ----------
    shards = {}
    for key in sorted(aidx):
        letter = key[:1].lower() if key[:1].isalpha() and key[:1].isascii() else '_'
        shards.setdefault(letter, {})[key] = aidx[key]
    for letter in sorted(shards):
        (out / 'authors' / 'idx' / f'{letter}.json').write_text(dumps(shards[letter]), encoding='utf-8')
    authors_report = (pkg / 'AUTHORS_REPORT.md').read_text(encoding='utf-8') if (pkg / 'AUTHORS_REPORT.md').exists() else ''
    render('authors.html', 'authors/index.html', '../', nav='authors', stats=stats, shard_letters=sorted(shards), n_index=len(aidx),
           authors_report_html=md_to_html(authors_report), issue_template=ISSUE_TEMPLATE,
           crumbs=[dict(label='Home', href='../index.html'), dict(label='Authors')])

    # ---------- methods ----------
    stage_counts = counts_sorted(st.decision_stage)
    route_counts = {k: int(v) for k, v in sorted(sd.route.value_counts().items())}
    gold_rows = [dict(field=r.field, gold_n=r.gold_n, covered=r.covered, correct=r.correct, coverage=f"{r.coverage:.3f}",
                      precision=f"{r.precision:.3f}", recall=f"{r.recall:.3f}") for r in gold.itertuples(index=False)]
    sp_prof = sw[sw.sp_profiled.fillna(False).astype(bool)]
    sp_stats = dict(n_low_complexity=int(sp_prof.sp_flag_low_complexity.fillna(False).astype(bool).sum()), n_low_depth=int(sp_prof.sp_low_depth.fillna(False).astype(bool).sum()),
                    n_partial=int(sp_prof.sp_partial.fillna(False).astype(bool).sum()), n_discordant=int(sp_prof.sp_runs_discordant.fillna(False).astype(bool).sum()),
                    median_spf=float(sp_prof.sp_spf.median()) if len(sp_prof) else None, median_ksf=float(sp_prof.sp_known_species_fraction.median()) if len(sp_prof) else None,
                    median_bifido=float(sp_prof.sp_ra_g_Bifidobacterium.median()) if len(sp_prof) else None,
                    version=str(sp_prof.sandpiper_version.dropna().iloc[0]) if len(sp_prof) else '', zenodo='20419175',
                    miss_reasons=[(k.replace('miss_', ''), int(spcov[k].sum())) for k in sorted(spcov.columns) if k.startswith('miss_') and k != 'miss_profiled'])
    render('methods.html', 'methods.html', '', nav='methods', stats=stats, status_counts=status_counts, stage_counts=stage_counts, sp=sp_stats,
           route_counts=route_counts, gold=gold_rows, flagdefs=flagdefs, flag_rows=flag_rows, docs=doc_list, crumbs=[dict(label='Home', href='index.html'), dict(label='Methods')])

    # ---------- releases (registry + notes + cite) ----------
    releases = []
    for r in reg.itertuples(index=False):
        d = {k: (v if v != '' else None) for k, v in r._asdict().items()}
        d['data_url'] = rspec['site_pages']['data_release_url'].format(data_tag=d['data_tag']) if d['data_tag'] else None
        d['site_url'] = rspec['site_pages']['site_release_url'].format(site_tag=d['site_tag']) if d['site_tag'] else None
        d['notes_html'] = md_to_html(notes_by_release[d['release_id']]) if d['release_id'] in notes_by_release else None
        d['changes_href'] = rspec['site_pages']['changes_release'].format(release_id=d['release_id']).split('/')[-1]
        d['current'] = d['release_id'] == release_id
        releases.append(d)
    releases_desc = list(reversed(releases))  # newest first on the page
    for d in releases:
        if d['notes_html'] is None:
            continue
        (out / 'releases' / f"RELEASE_NOTES_{d['release_id']}.md").write_text(notes_by_release[d['release_id']], encoding='utf-8')
    render('releases.html', rspec['site_pages']['releases_index'], '../', nav='releases', releases=releases_desc, n_releases=len(releases), first_numbered=rspec['release_id']['first_numbered'],
           crumbs=[dict(label='Home', href='../index.html'), dict(label='Releases')])

    # ---------- changes ("changed since <release>") ----------
    sw_n_by_study = sw.groupby('study_accession').size().to_dict()
    title_by_acc = uni.drop_duplicates('study_accession').set_index('study_accession').study_title.to_dict()
    # previous verdict per study = the last live verdict_norm in study_verdict_history that differs from the current verdict
    prev_verdict = {}
    for acc, g in svh_live.sort_values(['stage_rank', 'date'], kind='mergesort', na_position='last').groupby('study_accession'):
        prev_verdict[acc] = [str(v) for v in g.verdict_norm.dropna().tolist()]
    def changes_for(rid):
        v = uni_all[uni_all[RA].astype(str) == rid]
        verdicts = []
        for r in v.sort_values(['catalog_status', 'study_accession'], kind='mergesort').itertuples(index=False):
            d = r._asdict()
            cur = '' if isnull(d['triage_verdict']) else str(d['triage_verdict'])
            hist = [x for x in prev_verdict.get(d['study_accession'], []) if x != cur]
            verdicts.append(dict(acc=d['study_accession'], title='' if isnull(d['study_title']) else str(d['study_title'])[:120], verdict=cur, status='' if isnull(d['catalog_status']) else str(d['catalog_status']),
                                 previous=hist[-1] if hist else None, conf=None if isnull(d['confidence']) else round(float(d['confidence']), 2), stage='' if isnull(d['decision_stage']) else str(d['decision_stage']),
                                 included=d['study_accession'] in included, retired=None if isnull(d[RR]) else str(d[RR])))
        added = sda[sda[RA].astype(str) == rid]
        retired = sda[sda[RR].astype(str) == rid]
        def by_field(df_):
            return [dict(field=f, label=LABELS.get(f, f), link=f in FIELDS, n=int(n), n_samples=int(ns), n_studies=int(nst)) for f, n, ns, nst in
                    sorted(((f, len(g), g.sample_key.nunique(), g.study_accession.nunique()) for f, g in df_.groupby('field_name')), key=lambda x: (-x[1], x[0]))]
        both = pd.concat([added.assign(_kind='added'), retired.assign(_kind='retired')], ignore_index=True)
        per_study = []
        if len(both):
            g_ = both.groupby('study_accession')
            agg = pd.DataFrame(dict(n_added=g_._kind.apply(lambda x: int((x == 'added').sum())), n_retired=g_._kind.apply(lambda x: int((x == 'retired').sum())),
                                    n_samples=g_.sample_key.nunique(), fields=g_.field_name.apply(lambda x: ', '.join(sorted(set(x))))))
            agg['n_rows'] = agg.n_added + agg.n_retired
            agg = agg.sort_values(['n_rows', 'study_accession'], ascending=[False, True], kind='mergesort')
            reasons = retired.groupby('study_accession')[RREASON].apply(lambda x: '; '.join(sorted(set(str(v)[:80] for v in x.dropna()))[:3])).to_dict() if len(retired) else {}
            stages = both.groupby('study_accession')[RSTAGE].apply(lambda x: ', '.join(sorted(set(str(v) for v in x.dropna())))).to_dict()
            for acc, r in agg.head(20).iterrows():
                per_study.append(dict(acc=acc, included=acc in included, title=(title_by_acc.get(acc) or '')[:100], n_added=int(r.n_added), n_retired=int(r.n_retired), n_rows=int(r.n_rows),
                                      n_samples=int(r.n_samples), n_samples_study=int(sw_n_by_study.get(acc, 0)), fields=r.fields, reason=reasons.get(acc, ''), stage=stages.get(acc, '')))
        n_studies_changed = int(both.study_accession.nunique()) if len(both) else 0
        return dict(release_id=rid, verdicts=verdicts, n_verdicts=len(verdicts), n_verdict_studies=int(v.study_accession.nunique()),
                    n_added=len(added), n_retired=len(retired), n_samples_added=int(added.sample_key.nunique()), n_samples_retired=int(retired.sample_key.nunique()),
                    n_studies_changed=n_studies_changed, fields_added=by_field(added), fields_retired=by_field(retired), per_study=per_study,
                    retired_stages=counts_sorted(retired[RSTAGE].dropna().astype(str)) if len(retired) else [],
                    nothing=(len(verdicts) == 0 and len(added) == 0 and len(retired) == 0))
    changes = []
    for d in releases_desc:
        c = changes_for(d['release_id'])
        c.update(release_date=d['release_date'], package_version=d['package_version'], current=d['current'], href=d['changes_href'])
        changes.append(c)
        render('changes_release.html', rspec['site_pages']['changes_release'].format(release_id=d['release_id']), '../', nav='releases', c=c, rel=d,
               crumbs=[dict(label='Home', href='../index.html'), dict(label='Releases', href='../' + rspec['site_pages']['releases_index']), dict(label='Changes', href='index.html'), dict(label=d['release_id'])])
    render('changes_index.html', rspec['site_pages']['changes_index'], '../', nav='releases', changes=changes,
           crumbs=[dict(label='Home', href='../index.html'), dict(label='Releases', href='../' + rspec['site_pages']['releases_index']), dict(label='Changes')])
    for pth in [rspec['site_pages']['changes_index']] + [rspec['site_pages']['changes_release'].format(release_id=d['release_id']) for d in releases]:
        assert (out / pth).stat().st_size < 2_000_000, f'{pth} over the 2 MB budget'
    print(f'[{time.time()-t0:.0f}s] releases + {len(changes)} changes pages', file=sys.stderr)

    # ---------- contribute (R2026.2: read-only worklist, MATURITY_PLAN §3.2) ----------
    if has_contribute:
        n_missing_by_field = {f: int(sum(1 for r in wl_rows if f in r['missing'])) for f in CFIELDS.values()}
        blockers = [dict(code=c, label=BLABEL[c], n=n) for c, n in counts_sorted(wl.blocker_code)]
        types = [dict(code=c, label=TLABEL[c], n=int((wl.contribution_type == c).sum())) for c in cspec['contribution_types']]
        cs = dict(n_open=len(wl), n_include=int((wl.triage_verdict == 'include').sum()), n_uncertain=int((wl.triage_verdict == 'uncertain').sum()),
                  n_samples=int(wl.n_samples.sum()), n_catalog_scope=int(wl.n_catalog_scope.sum()), n_field_gaps=int(wl.n_missing_fields.sum()),
                  threshold=float(cspec['missing_threshold']), blockers=blockers, types=types,
                  fields=[dict(name=f, short=k, label=LABELS.get(f, f), n_missing=n_missing_by_field[f]) for k, f in CFIELDS.items()],
                  weights=[(k, cspec['field_weights'][k]) for k in CFIELDS], repo=cspec['issue_form']['repo'],
                  issues_list_url=f"https://github.com/{cspec['issue_form']['repo']}/issues?q=is%3Aissue+label%3A{cspec['issue_form']['label']}")
        assert cs['n_field_gaps'] == sum(n_missing_by_field.values()), 'F13: field-gap count differs between the worklist and the fields table'
        assert cs['n_field_gaps'] == int((wlf.coverage < cs['threshold']).sum()), 'F13: worklist n_missing_fields disagrees with worklist_fields coverage'
        render('contribute.html', site['contribute_page'], '../', nav='contribute', rows=wl_rows, cs=cs,
               crumbs=[dict(label='Home', href='../index.html'), dict(label='Contribute')])
        wjson = [dict(rank=int(r['rank']), acc=r['study_accession'], title=r.get('study_title') or '', cohort=r.get('cohort_name') or '', verdict=r['triage_verdict'],
                      n=int(r['n_samples']), ncs=int(r['n_catalog_scope']), missing=r['missing'], blocker=r['blocker_code'], detail=r.get('blocker_detail') or '', unlock=r.get('unlock_text') or '',
                      type=r['contribution_type'], papers=int(r['n_linked_papers']), pmids=r['pmids'], score=float(r['priority_score']), issue_url=r['issue_url'],
                      coverage={k: float(r.get(f'coverage_{k}') or 0) for k in CFIELDS}, tier={k: str(r.get(f'best_tier_{k}') or 'R0') for k in CFIELDS}) for r in wl_rows]
        (out / 'data' / 'contribute_worklist.json').write_text(dumps(wjson), encoding='utf-8')
        assert (out / site['contribute_page']).stat().st_size < 2_000_000, 'contribute/index.html over the 2 MB budget'
        _html = (out / site['contribute_page']).read_text(encoding='utf-8')
        assert _html.count('class="btn xs contribute"') == len(wl), 'contribute page must carry one Contribute button per worklist study'
        print(f'[{time.time()-t0:.0f}s] contribute page: {len(wl)} studies', file=sys.stderr)

    # ---------- downloads + manifest ----------
    def dirstat(sub, pattern='*'):
        fs = [f for f in (out / sub).glob(pattern) if f.is_file()]
        return dict(n=len(fs), size=human(sum(f.stat().st_size for f in fs)), bytes=sum(f.stat().st_size for f in fs))
    sitedata = [
        dict(path='data/sample_metadata_wide.parquet', desc='Sample table loaded by the explorer', **dirstat('data', 'sample_metadata_wide.parquet')),
        dict(path='data/sample_determinations.parquet', desc='Evidence rows loaded by the explorer on demand', **dirstat('data', 'sample_determinations.parquet')),
        dict(path='data/value_history.parquet', desc='Superseded / rejected / dropped values, loaded by the explorer on demand', **dirstat('data', 'value_history.parquet')),
        dict(path='data/' + rspec['files']['determinations_all'], desc='Bitemporal determinations (current + retired, release_added / release_retired), loaded by the explorer value timeline on demand', **dirstat('data', rspec['files']['determinations_all'])),
        dict(path='data/sandpiper_top_genera.parquet', desc='Top genera per sample, loaded by the explorer on demand', **dirstat('data', 'sandpiper_top_genera.parquet')),
        dict(path='data/studies/<PRJ>.csv.gz|.parquet', desc='Per-study sample slices (gzip CSV + parquet)', **dirstat('data/studies', '*[0-9].csv.gz')),
        dict(path='data/studies/<PRJ>_determinations.csv.gz', desc='Per-study determinations with evidence (gzip CSV, mtime 0)', **dirstat('data/studies', '*_determinations.csv.gz')),
        dict(path='data/cohorts/<COH>.csv.gz|.parquet', desc='Per-cohort sample slices (multi-study cohorts)', **dirstat('data/cohorts')),
        dict(path='data/package/', desc='The complete package, file by file, plus the zip', **dirstat('data/package')),
        dict(path='authors/idx/<letter>.json', desc='Author index shards', **dirstat('authors/idx')),
    ] + ([dict(path='data/contribute_worklist.json', desc='Contribution worklist (one object per open study; same content as contribute_worklist.csv)', **dirstat('data', 'contribute_worklist.json'))] if has_contribute else [])
    offsite = [dict(o, desc=o['desc'].replace('{v}', version)) for o in OFFSITE]
    render('downloads.html', 'downloads.html', '', nav='downloads', files=pkg_files, zip_name=zip_name, zip_size=zip_size, sitedata=sitedata, offsite=offsite, vj=vj,
           crumbs=[dict(label='Home', href='index.html'), dict(label='Downloads')])
    manifest = dict(site=site['title'], package_version=version, release_tag=vj['release_tag'], release_id=release_id, build_date=build_date, generator_git_sha=gen_sha, base_url=base_url,
                    files=[dict(path=str(p.relative_to(out)), bytes=p.stat().st_size, sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted((out / 'data').rglob('*')) if p.is_file()],
                    tables={k: dict(rows=v.get('rows'), sha256=v.get('sha256')) for k, v in sorted(vj['tables'].items())})
    (out / 'data' / 'manifest.json').write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding='utf-8')
    (out / 'data' / 'VERSION.json').write_text(json.dumps(vj, indent=1, sort_keys=True), encoding='utf-8')

    # ---------- home, search index, sitemap ----------
    sidx = [dict(t='study', id=s['study_accession'], n=s['study_title'] or '', u=f"studies/{s['study_accession']}.html",
                 k=f"{s['study_accession']} {s['study_title'] or ''} {s['cohort_name'] or ''} {s.get('first_author') or ''}".lower()) for s in studies]
    sidx += [dict(t='cohort', id=c['cohort_id'], n=c['cohort_name'], u=f"cohorts/{c['cohort_id']}.html",
                  k=f"{c['cohort_id']} {c['cohort_name']} {c.get('study_accessions') or ''}".lower()) for c in cohorts]
    (out / 'search_index.json').write_text(dumps(sidx), encoding='utf-8')
    render('index.html', 'index.html', '', nav='home', stats=stats, readme_version_warning=readme_version_warning, n_releases=len(releases))
    urls = ''.join(f'<url><loc>{base_url}{p}</loc></url>' for p in sorted(written))  # F21: docs pages included
    (out / 'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + urls + '</urlset>', encoding='utf-8')
    (out / 'robots.txt').write_text(f'User-agent: *\nAllow: /\nSitemap: {base_url}sitemap.xml\n', encoding='utf-8')
    # F7 / F1: nothing published may carry a session identifier, a planning doc, an SRA submission id or an e-mail address in an organisation line
    for name in NEVER_PUBLISH_DOCS:
        assert not (out / 'docs' / name).exists() and not (out / 'docs' / (name[:-3] + '.html')).exists(), f'F7: {name} must not be published'
    leak_pages = []
    for p in sorted(out.rglob('*.html')):
        t = p.read_text(encoding='utf-8')
        if re.search(r'\b(?:frame|session)\s+[0-9a-f]{8}\b', t) or re.search(r'Organisations: [^<]*(?:SUB\d{6,}|@)', t):
            leak_pages.append(str(p.relative_to(out)))
    assert not leak_pages, f'F7/F1 leak check failed on {leak_pages[:5]}'
    total = sum(p.stat().st_size for p in out.rglob('*') if p.is_file())
    largest = max((p for p in out.rglob('*') if p.is_file()), key=lambda p: (p.stat().st_size, str(p)))
    print(json.dumps(dict(pages=len(written), total_bytes=total, total_human=human(total), largest=str(largest.relative_to(out)),
                          largest_bytes=largest.stat().st_size, seconds=round(time.time() - t0, 1), version=version, build_date=build_date,
                          stats={k: v for k, v in stats.items() if not isinstance(v, list)}), sort_keys=True), file=sys.stderr)


if __name__ == '__main__':
    main()

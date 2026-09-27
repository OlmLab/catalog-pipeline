#!/usr/bin/env python
"""Build a MOCK 1.6.0 (R2026.4) package from an unpacked 1.5.0 package by adding the registry-tier tables in the FROZEN
registry schema of config/scope.yaml + config/vocab/*.yaml. Used by the Site track (scaleup/S1-site) to develop and test
registry/ before the S0 track's real `src/catalog/registry` output exists. NOTHING here is a curated value.

Usage: python make_mock_registry_package.py --src data/inputs/data_package --out build/mock_package_1.6.0

Two kinds of rows (column `universe_slice` tells them apart):
  * the 9,581 infant-universe studies (universe_studies_all.parquet, current verdict rows) with DETERMINISTIC PRIORS:
      host_human    <- reason_code (host_nonhuman / host_environmental / host_synthetic -> no; else yes)
      assay         <- reason_code assay_* (else shotgun_dna: the universe was enumerated as METAGENOMIC WGS/WXS)
      body_sites    <- body_site_call text, else whole-word vocabulary terms in study_title, else unknown_site
      life_stages   <- triage verdict / age_* reason code, else vocabulary terms in study_title, else unknown_age
      ENA aggregates (library_strategies, instrument_platforms, host_tax_ids, scientific_names_top, center_name,
      secondary_study_accession) are computed from runs.parquet for the 389 included studies and left NULL otherwise
      (omit rather than guess). Every committed site/stage value carries an evidence row {source, quote<=12 words}.
      classification_stage = deterministic_prior, confidence 0.6 (reason-code derived) / 0.5 (title-term derived).
  * ~2,400 SYNTHETIC 'signal_human_new' rows with accessions PRJMOCK000001… (not INSDC-shaped on purpose), titles
      prefixed '[MOCK]', plausible body-site / life-stage / assay / stage distributions (SCALE_UP_PLAN §1 proportions),
      in_infant_catalog = not_screened. They exist only so the registry pages and explorer can be exercised at scale.
Also written: registry_universe_audit.csv (per-slice counts; the real file comes from the S0 sweep), releases.csv row
R2026.4, RELEASE_NOTES_R2026.4.md, VERSION.json (release_id R2026.4 / package_version 1.6.0 / previous R2026.3).
"""
import argparse, hashlib, json, re, sys
from pathlib import Path
import numpy as np
import pandas as pd
import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
MOCK_SLICE = 'signal_human_new'


def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load_vocab(vocab_dir):
    return {n: yaml.safe_load((vocab_dir / {'body_site': 'body_sites.yaml', 'life_stage': 'life_stages.yaml', 'assay': 'assay.yaml', 'population_flags': 'population_flags.yaml'}[n]).read_text(encoding='utf-8')) for n in ('body_site', 'life_stage', 'assay', 'population_flags')}


def term_hits(text, codes, skip=()):
    """whole-word / stem-prefix matches of vocabulary terms in `text` -> [(code, matched span)] in code order; negatives block."""
    out = []
    if not text:
        return out
    low = str(text).lower()
    for code, spec in codes.items():
        if code in skip or not spec.get('terms'):
            continue
        if any(n in low for n in spec.get('negatives', [])):
            continue
        for t in spec['terms']:
            m = re.search(r'\b' + re.escape(str(t).lower()) + r'\w*', low)
            if m:
                # quote = the shortest span of the title (<= 12 words) around the hit
                words = str(text).split()
                idx = next((i for i, w in enumerate(words) if m.group(0)[:len(t)] in w.lower()), 0)
                out.append((code, ' '.join(words[max(0, idx - 3): idx + 4])[:120]))
                break
    return out


def q12(s):
    return ' '.join(str(s).split()[:12])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--scope-config', default=str(REPO / 'config' / 'scope.yaml'))
    ap.add_argument('--releases-config', default=str(REPO / 'config' / 'releases.yaml'))
    ap.add_argument('--release-date', default='2026-10-31')
    ap.add_argument('--n-synthetic', type=int, default=2400)
    ap.add_argument('--seed', type=int, default=20261031)
    a = ap.parse_args()
    src, out = Path(a.src), Path(a.out)
    scope = yaml.safe_load(Path(a.scope_config).read_text(encoding='utf-8'))
    rspec = yaml.safe_load(Path(a.releases_config).read_text(encoding='utf-8'))
    V = load_vocab(REPO / scope['vocab_dir'])
    RA, RR, PA = rspec['columns']['release_added'], rspec['columns']['release_retired'], rspec['columns']['package_added']
    RID, PV = scope['release_id'], str(scope['package_version'])
    COLS = list(scope['registry_columns'])
    out.mkdir(parents=True, exist_ok=True)
    for f in sorted(src.iterdir()):
        if f.is_file():
            (out / f.name).write_bytes(f.read_bytes())

    uni = pd.read_parquet(src / 'universe_studies_all.parquet')
    uni = uni[uni[RR].isna()] if RR in uni.columns else uni
    assert uni.study_accession.is_unique
    runs = pd.read_parquet(src / 'runs.parquet')
    included = set(pd.read_parquet(src / 'study_metadata_wide.parquet', columns=['study_accession']).study_accession)

    # ---- ENA aggregates for the included studies (real archive fields from runs.parquet) ----
    def top5(s):
        vc = s.dropna().astype(str).value_counts().head(5)
        return ';'.join(f'{k} ({v})' for k, v in vc.items()) if len(vc) else None
    def joined(s):
        vals = sorted(set(s.dropna().astype(str)) - {''})
        return ';'.join(vals) if vals else None
    agg = runs.groupby('study_accession').agg(
        secondary_study_accession=('secondary_study_accession', lambda s: joined(s)),
        center_name=('center_name', lambda s: s.dropna().astype(str).mode().iloc[0] if s.notna().any() else None),
        first_public_max=('first_public', lambda s: str(s.dropna().max())[:10] if s.notna().any() else None),
        library_strategies=('library_strategy', joined), library_sources=('library_source', joined),
        instrument_platforms=('instrument_platform', joined), scientific_names_top=('scientific_name', top5),
        host_tax_ids=('host_tax_id', lambda s: joined(s.dropna().astype(str).str.replace(r'\.0$', '', regex=True))),
        n_runs_host_9606=('host_tax_id', lambda s: int((s.astype(str).str.replace(r'\.0$', '', regex=True) == '9606').sum())),
        n_runs_nonhuman_host=('host_tax_id', lambda s: int((s.notna() & (s.astype(str).str.replace(r'\.0$', '', regex=True) != '9606')).sum())),
    )

    HOST_NO = {'host_nonhuman', 'host_environmental', 'host_synthetic'}
    ASSAY = {'assay_amplicon': 'amplicon', 'assay_amplicon_misfiled': 'amplicon_misfiled', 'assay_rna': 'rna', 'assay_isolate_genome': 'isolate_genome',
             'assay_other_nonshotgun': 'other', 'assay_assembly_only': 'assembly_only'}
    BS_CODES, LS_CODES = V['body_site']['codes'], V['life_stage']['codes']
    rows = []
    for r in uni.sort_values('study_accession').itertuples(index=False):
        d = r._asdict()
        rc = None if pd.isna(d.get('reason_code')) else str(d['reason_code'])
        verdict = str(d['triage_verdict'])
        title = '' if pd.isna(d.get('study_title')) else str(d['study_title'])
        host = 'no' if rc in HOST_NO else 'yes'
        host_ev = [dict(source='external_curation.infant_triage', quote=q12(f'reason_code {rc}' if rc else f'verdict {verdict}'))]
        assay = ASSAY.get(rc, 'shotgun_dna')
        # body sites
        sites, bs_ev = [], []
        call = None if pd.isna(d.get('body_site_call')) else str(d['body_site_call'])
        if host == 'yes':
            if call and call not in ('unstated', 'unknown', 'excluded_site', 'other_linked'):
                for code, span in term_hits(call, BS_CODES):
                    sites.append(code); bs_ev.append(dict(source='external_curation.infant_triage', quote=q12(f'body_site_call {call}')))
            if not sites:
                for code, span in term_hits(title, BS_CODES):
                    sites.append(code); bs_ev.append(dict(source='study.title', quote=q12(span)))
            if not sites:
                if rc == 'site_excluded':
                    sites = ['other_site']; bs_ev = [dict(source='external_curation.infant_triage', quote=q12(f'reason_code site_excluded; body_site_call {call or "null"}'))]
                else:
                    sites = ['unknown_site']
        sites = list(dict.fromkeys(sites))
        # life stages
        stages, ls_ev, flags = [], [], []
        if host == 'yes':
            if verdict == 'include':
                stages = ['infant']; ls_ev = [dict(source='external_curation.infant_triage', quote='verdict include (age 0–1,100 d evidenced)')]
                for code, span in term_hits(title, {'neonate': LS_CODES['neonate']}):
                    stages.append('neonate'); ls_ev.append(dict(source='study.title', quote=q12(span)))
            elif rc == 'age_adult_only':
                stages = ['adult']; ls_ev = [dict(source='external_curation.infant_triage', quote='reason_code age_adult_only')]
            elif rc == 'age_child_over_36m':
                stages = ['child']; ls_ev = [dict(source='external_curation.infant_triage', quote='reason_code age_child_over_36m')]
            elif rc == 'age_maternal_only':
                stages = ['adult']; flags = ['pregnant']; ls_ev = [dict(source='external_curation.infant_triage', quote='reason_code age_maternal_only')]
            else:
                for code, span in term_hits(title, LS_CODES):
                    stages.append(code); ls_ev.append(dict(source='study.title', quote=q12(span)))
            if not stages:
                stages = ['unknown_age']
            if verdict == 'uncertain' and 'infant' not in stages:
                stages = [s for s in stages if s != 'unknown_age'] + ['unknown_age'] if stages == ['unknown_age'] else stages
        stages = list(dict.fromkeys(stages))
        for code, span in term_hits(title, {'hospitalised': dict(terms=['NICU', 'hospitali', 'intensive care']), 'twins': dict(terms=['twin']),
                                            'mother_infant_pair': dict(terms=['mother-infant', 'mother–infant', 'maternal-infant', 'dyad']),
                                            'pregnant': dict(terms=['pregnan']), 'antibiotic_trial': dict(terms=['randomi', 'trial'])}):
            if host == 'yes' and code not in flags:
                flags.append(code)
        conf = 0.6 if (rc or verdict == 'include') else 0.5
        if any(e['source'] == 'study.title' for e in bs_ev + ls_ev) and not rc:
            conf = 0.5
        n_runs = None if pd.isna(d.get('n_runs')) else int(d['n_runs'])
        rows.append(dict(
            study_accession=d['study_accession'], secondary_study_accession=agg.secondary_study_accession.get(d['study_accession']), study_title=title or None,
            description_short=None, center_name=agg.center_name.get(d['study_accession']),
            first_public_min=None if pd.isna(d.get('first_public_min')) else str(d['first_public_min'])[:10], first_public_max=agg.first_public_max.get(d['study_accession']),
            n_runs=n_runs, n_samples=None if pd.isna(d.get('n_samples')) else int(d['n_samples']), n_biosamples=None if pd.isna(d.get('n_biosamples')) else int(d['n_biosamples']),
            library_strategies=agg.library_strategies.get(d['study_accession']), library_sources=agg.library_sources.get(d['study_accession']),
            instrument_platforms=agg.instrument_platforms.get(d['study_accession']), scientific_names_top=agg.scientific_names_top.get(d['study_accession']),
            host_tax_ids=agg.host_tax_ids.get(d['study_accession']),
            n_runs_host_9606=None if d['study_accession'] not in agg.index else int(agg.n_runs_host_9606[d['study_accession']]),
            n_runs_nonhuman_host=None if d['study_accession'] not in agg.index else int(agg.n_runs_nonhuman_host[d['study_accession']]),
            human_signal=host == 'yes', human_signal_rule='B' if host == 'yes' else 'none', ambiguous=bool(verdict == 'uncertain'),
            host_human=host, host_evidence=json.dumps(host_ev, ensure_ascii=False), assay=assay,
            access='controlled' if d.get('controlled_access') is True else ('open' if d.get('controlled_access') is False else 'unknown'),
            body_sites=';'.join(sites) if sites else None, body_site_primary=sites[0] if sites else None, body_site_evidence=json.dumps(bs_ev, ensure_ascii=False),
            life_stages=';'.join(stages) if stages else None, life_stage_primary=stages[0] if stages else None, life_stage_evidence=json.dumps(ls_ev, ensure_ascii=False),
            population_flags=';'.join(flags) if flags else None, health_context=None,
            classification_stage='deterministic_prior', classification_confidence=conf, classification_model='deterministic',
            in_infant_catalog=verdict, infant_reason_code=rc, universe_slice=str(d['universe_slice'])))
    real = pd.DataFrame(rows)

    # ---- synthetic rows ----
    rng = np.random.default_rng(a.seed)
    n = a.n_synthetic
    site_p = [('gut_stool', .44), ('oral', .12), ('nasal_nasopharyngeal', .07), ('respiratory_lower', .05), ('skin', .05), ('vaginal_urogenital', .05), ('blood_tissue', .04), ('milk', .01), ('eye_ear', .01), ('unknown_site', .16)]
    stage_p = [('adult', .50), ('child', .08), ('infant', .06), ('neonate', .02), ('elderly', .05), ('adolescent', .02), ('mixed_ages', .08), ('unknown_age', .19)]
    stg_p = [('deterministic_prior', .30), ('sonnet_x2', .45), ('opus_adjudicated', .05), ('pending', .20)]
    host_p = [('yes', .85), ('mixed', .05), ('unknown', .10)]
    assay_p = [('shotgun_dna', .90), ('amplicon_misfiled', .03), ('other', .03), ('mixed', .02), ('isolate_genome', .02)]
    acc_p = [('open', .95), ('controlled', .03), ('unknown', .02)]
    plat_p = [('ILLUMINA', .88), ('ILLUMINA;OXFORD_NANOPORE', .05), ('BGISEQ', .04), ('DNBSEQ', .02), ('OXFORD_NANOPORE', .01)]
    ctx_by_site = {'gut_stool': ['IBD cohort', 'type 2 diabetes', 'colorectal cancer screening', 'healthy adults', 'FMT trial', 'antibiotic perturbation'],
                   'oral': ['periodontitis', 'caries', 'healthy volunteers'], 'skin': ['atopic dermatitis', 'healthy skin'], 'vaginal_urogenital': ['bacterial vaginosis', 'pregnancy cohort'],
                   'respiratory_lower': ['cystic fibrosis', 'ventilator-associated pneumonia'], 'nasal_nasopharyngeal': ['respiratory infection cohort'], 'blood_tissue': ['sepsis', 'tumour tissue'], 'milk': ['lactation cohort']}
    def pick(p):
        keys, w = zip(*p); return rng.choice(keys, p=np.array(w) / sum(w))
    SL, LL = {k: v['label'] for k, v in BS_CODES.items()}, {k: v['label'] for k, v in LS_CODES.items()}
    srows = []
    for i in range(n):
        acc = f'PRJMOCK{i + 1:06d}'
        site, stage, stg, host = str(pick(site_p)), str(pick(stage_p)), str(pick(stg_p)), str(pick(host_p))
        sites = [site]
        if rng.random() < 0.12 and site != 'unknown_site':
            extra = str(pick([p for p in site_p if p[0] not in (site, 'unknown_site')])); sites.append(extra)
        stages = [stage] if stage != 'mixed_ages' else ['adult', 'child', 'mixed_ages']
        if stage == 'neonate' and rng.random() < 0.5:
            stages.append('infant')
        nr = int(np.clip(rng.lognormal(3.6, 1.3), 2, 12000))
        nb = int(max(1, round(nr / rng.choice([1, 1, 1, 2, 3]))))
        year = int(rng.integers(2012, 2027)); mon = int(rng.integers(1, 13))
        assay = str(pick(assay_p))
        flags = []
        if rng.random() < 0.35:
            flags.append(str(rng.choice(list(V['population_flags']['codes']))))
        ctx = str(rng.choice(ctx_by_site.get(site, ['not stated'])))
        title = f'[MOCK] Shotgun metagenomes of {LL.get(stage, stage).split(" (")[0].lower()} {SL[site].lower()} samples — {ctx} (synthetic study {i + 1})'
        pending = stg == 'pending'
        conf = None if pending else float(np.round({'deterministic_prior': 0.6, 'sonnet_x2': rng.uniform(0.6, 0.95), 'opus_adjudicated': rng.uniform(0.7, 0.98)}[stg], 2))
        ev = lambda src, q: json.dumps([dict(source=src, quote=q12(q))], ensure_ascii=False)
        srows.append(dict(
            study_accession=acc, secondary_study_accession=None, study_title=title, description_short=f'[MOCK] synthetic registry row for site-generator tests; {ctx}.', center_name='MOCK CENTER',
            first_public_min=f'{year}-{mon:02d}-01', first_public_max=f'{year}-{mon:02d}-28', n_runs=nr, n_samples=nb, n_biosamples=nb,
            library_strategies='WGS' if assay in ('shotgun_dna', 'amplicon_misfiled') else ('WGS;AMPLICON' if assay == 'mixed' else 'OTHER' if assay == 'other' else 'WGS'),
            library_sources='GENOMIC' if assay == 'isolate_genome' else 'METAGENOMIC', instrument_platforms=str(pick(plat_p)),
            scientific_names_top=f'human {SL[site].split(" /")[0].lower()} metagenome ({nr})' if site != 'unknown_site' else f'human metagenome ({nr})',
            host_tax_ids='9606' if host == 'yes' else ('9606;10090' if host == 'mixed' else None),
            n_runs_host_9606=nr if host == 'yes' else (nr // 2 if host == 'mixed' else 0), n_runs_nonhuman_host=0 if host != 'mixed' else nr - nr // 2,
            human_signal=True, human_signal_rule='A' if host == 'yes' else 'B', ambiguous=host != 'yes',
            host_human=host, host_evidence=ev('sample.attr.host_tax_id', '9606' if host != 'unknown' else 'missing'), assay=assay, access=str(pick(acc_p)),
            body_sites=';'.join(sites), body_site_primary=sites[0], body_site_evidence='[]' if pending else ev('study.title', f'{SL[site].lower()} samples'),
            life_stages=';'.join(stages), life_stage_primary=stages[0], life_stage_evidence='[]' if pending else ev('study.title', LL.get(stage, stage).split(' (')[0].lower()),
            population_flags=';'.join(flags) if flags else None, health_context=None if pending else ctx,
            classification_stage=stg, classification_confidence=conf, classification_model=None if pending else {'deterministic_prior': 'deterministic', 'sonnet_x2': 'sonnet (mock)', 'opus_adjudicated': 'opus (mock)'}[stg],
            in_infant_catalog='not_screened', infant_reason_code=None, universe_slice=MOCK_SLICE))
    synth = pd.DataFrame(srows)
    reg = pd.concat([real, synth], ignore_index=True)

    # ---- scope memberships (deterministic from host/sites/stages/assay; config/scope.yaml rules) ----
    def memberships(r):
        if r['host_human'] == 'no':
            return None
        sites = set(str(r['body_sites'] or '').split(';')) - {''}
        stages = set(str(r['life_stages'] or '').split(';')) - {''}
        m = []
        if r['in_infant_catalog'] == 'include':
            m.append('infant_gut')
        if 'gut_stool' in sites and stages & {'child', 'adolescent'}:
            m.append('gut_child')
        if 'gut_stool' in sites and stages & {'adult', 'elderly'}:
            m.append('gut_adult')
        for sid, code in [('oral', 'oral'), ('skin', 'skin'), ('vaginal_urogenital', 'vaginal_urogenital'), ('milk', 'milk'), ('blood_tissue', 'blood_tissue')]:
            if code in sites:
                m.append(sid)
        if sites & {'nasal_nasopharyngeal', 'respiratory_lower'}:
            m.append('respiratory')
        if sites & {'other_site', 'eye_ear'}:
            m.append('other_site')
        if not sites or 'unknown_site' in sites:
            m.append('unknown_site')
        return ';'.join(m) if m else None
    reg['scope_memberships'] = reg.apply(memberships, axis=1)
    reg[RA], reg[RR], reg[PA] = RID, None, PV
    for c in ('n_runs', 'n_samples', 'n_biosamples', 'n_runs_host_9606', 'n_runs_nonhuman_host'):
        reg[c] = reg[c].astype('Int64')
    reg['classification_confidence'] = reg['classification_confidence'].astype('float64')
    reg = reg[COLS].sort_values('study_accession', kind='mergesort').reset_index(drop=True)
    assert reg.study_accession.is_unique and list(reg.columns) == COLS
    assert set(reg.classification_stage) <= set(scope['classification_stages']) and set(reg.host_human) <= set(scope['host_human_values'])
    assert set(reg.assay) <= set(scope['assay_values']) and set(reg.in_infant_catalog) <= set(scope['in_infant_catalog_values'])
    reg.to_parquet(out / scope['files']['studies'], index=False)

    # ---- per-slice audit (MOCK: ENA counts are the pulled counts; the S0 sweep writes the real file) ----
    aud = []
    for sl, g in reg.groupby('universe_slice', sort=True):
        nr = int(g.n_runs.fillna(0).sum())
        aud.append(dict(universe_slice=sl, ena_query='(mock) library_source=METAGENOMIC AND library_strategy in (WGS,WXS)' if sl == MOCK_SLICE else '(mock) infant universe slice',
                        ena_count_runs=nr, rows_pulled=nr, n_studies=len(g), completeness=1.0 if nr else None, pulled_at=a.release_date))
    pd.DataFrame(aud, columns=scope['audit_columns']).to_csv(out / scope['files']['audit'], index=False)

    # ---- release registry, notes, VERSION.json, README heading ----
    regcsv = pd.read_csv(src / rspec['files']['registry'], dtype=str, keep_default_na=False)
    prev = regcsv.iloc[-1].to_dict()
    new = dict(prev, release_id=RID, package_version=PV, release_date=a.release_date, data_tag=f'data-v{PV}', site_tag=f'site-v{PV}', doi='',
               notes_file=rspec['files']['release_notes_pattern'].format(release_id=RID))
    regcsv = pd.concat([regcsv, pd.DataFrame([new])[regcsv.columns]], ignore_index=True)
    regcsv.to_csv(out / rspec['files']['registry'], index=False)
    n_real, n_syn = int((reg.universe_slice != MOCK_SLICE).sum()), int((reg.universe_slice == MOCK_SLICE).sum())
    (out / new['notes_file']).write_text(f"""# Release notes — {RID} (data package {PV}, {a.release_date})

*MOCK release notes written by site_generator/gen/tests/make_mock_registry_package.py; the registry (S0) track's `make release` writes the real file.*

## Registry tier (new)
First release of the registry tier: `registry_studies.parquet` ({len(reg):,} rows = {n_real:,} infant-universe studies with deterministic priors + {n_syn:,} synthetic `{MOCK_SLICE}` rows that exist only in this mock), `registry_universe_audit.csv`. Column order and vocabularies: config/scope.yaml, config/vocab/*.yaml. `registry_runs.parquet` is a Release asset, not a site file.

## New studies
None in the infant catalog (mock).

## Verdict changes
None (mock).

## Schema
Columns {RA}, {RR}, {PA} appended to the registry tables (release_added = {RID}).
""", encoding='utf-8')
    vj = json.loads((src / 'VERSION.json').read_text())
    vj['previous_version'] = vj['package_version']
    vj['previous_release_id'] = vj['release_id']
    vj['package_version'] = PV
    vj['release_tag'] = f'data-v{PV}'
    vj['release_id'] = RID
    vj['build_date'] = a.release_date
    vj['mock'] = 'placeholder registry tables — site_generator/gen/tests/make_mock_registry_package.py'
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
    readme = (out / 'README.md').read_text(encoding='utf-8')
    readme = re.sub(r'data package v\d+\.\d+\.\d+', f'data package v{PV}', readme, count=1)
    (out / 'README.md').write_text(readme, encoding='utf-8')
    summary = dict(out=str(out), n_registry=len(reg), n_real=n_real, n_synthetic=n_syn,
                   host_human=reg.host_human.value_counts().to_dict(), stage=reg.classification_stage.value_counts().to_dict(),
                   body_site_primary={str(k): int(v) for k, v in reg.body_site_primary.value_counts(dropna=False).head(12).items()}, life_stage_primary={str(k): int(v) for k, v in reg.life_stage_primary.value_counts(dropna=False).items()},
                   assay=reg.assay.value_counts().to_dict())
    print(json.dumps(summary, default=str, sort_keys=True))


if __name__ == '__main__':
    main()

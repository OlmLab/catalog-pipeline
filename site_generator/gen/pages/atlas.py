"""Atlas pages (R2026.12): taxon world map + data-driven observations.

Two entry points:

* ``precompute(genus_long, species_long, summary, wide, out_dir, ...)`` turns the Sandpiper long tables and the
  package wide table into the static atlas payload under ``out_dir`` (``taxa.json``, ``countries.json``,
  ``studies.json``, ``matrix_<rank>.bin``, ``country_hdi.csv``).  Pure pandas/numpy; ~30 s on the full catalog.
* ``build(env, render, ctx, out_dir)`` copies a precomputed payload (``ctx['atlas_data_dir']``) to
  ``<out_dir>/data/atlas/`` and renders ``atlas/index.html`` + ``atlas/observations.html``.  The observations page is
  generated from ``data/atlas/observations.json`` (cards written by scripts/atlas_observations.py); when that file is
  missing the page renders with an empty card list so the build never breaks.

Payload format (also written to ``taxa.json -> meta.format``):
``matrix_<rank>.bin`` is a little-endian uint32 stream.  For each taxon of that rank, in ``taxa.json`` order:
``nC, nS`` then ``nC`` triples ``(country_i, n_present, mean_relabund_x1e6)`` then ``nS`` triples
``(study_i, n_present, mean_relabund_x1e6)``.  ``n_present`` counts samples with relabund >= ``presence_threshold``
(1e-4; species table: 1e-3 because it is released at that cut); the mean is over ALL samples of the country/study,
so prevalence = n_present / countries[i].n.  Pairs with ``n_present == 0`` are omitted.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
RANKS = ['phylum', 'class', 'order', 'family', 'genus', 'species']
PREFIX = {'phylum': 'p__', 'class': 'c__', 'order': 'o__', 'family': 'f__', 'genus': 'g__', 'species': 's__'}
AGE_CATS = ['neonate', 'infant', 'child', 'adolescent', 'adult', 'elderly', 'unknown']
PRESENCE = 1e-4
SPECIES_PRESENCE = 1e-3
MIN_COUNTRY_SAMPLES = 30
# countries that the 110 m Natural Earth base map does not carry as their own polygon -> drawn as dots
POINT_COUNTRIES = {'HK': (114.17, 22.32), 'SG': (103.82, 1.35), 'BB': (-59.54, 13.19), 'GF': (-53.1, 3.9), 'IO': (72.4, -7.3), 'TC': (-71.8, 21.7)}

# UNDP Human Development Report 2023/24 (HDI for 2022), TRANSCRIBED FROM MEMORY, rounded to 2 decimals, UNVERIFIED -
# hdr.undp.org was not reachable from the build sandbox.  Replace with the official CSV when available.
HDI_2022 = dict(AE=0.94, AR=0.85, AT=0.93, AU=0.95, BB=0.81, BD=0.67, BE=0.94, BF=0.44, BG=0.80, BR=0.76, BS=0.82, BW=0.71, CA=0.94, CD=0.48,
                CF=0.39, CG=0.65, CH=0.97, CL=0.86, CM=0.59, CN=0.79, CO=0.76, CY=0.91, CZ=0.90, DE=0.95, DK=0.95, EC=0.77, EE=0.90, EG=0.73,
                ES=0.91, ET=0.49, FI=0.94, FJ=0.73, FR=0.91, GA=0.69, GB=0.94, GH=0.60, GR=0.89, GW=0.48, HK=0.96, HN=0.62, HR=0.88, HT=0.55,
                HU=0.85, ID=0.71, IE=0.95, IL=0.92, IN=0.64, IR=0.78, IS=0.96, IT=0.91, JP=0.92, KE=0.60, KH=0.60, KR=0.93, KZ=0.80, LA=0.62,
                LR=0.49, LU=0.93, MG=0.49, ML=0.41, MM=0.61, MN=0.74, MW=0.51, MX=0.78, MY=0.81, MZ=0.46, NE=0.39, NG=0.55, NI=0.67, NL=0.95,
                NO=0.97, NP=0.60, NZ=0.94, PA=0.82, PE=0.76, PL=0.88, PT=0.87, RO=0.83, RS=0.81, RU=0.82, SA=0.88, SE=0.95, SG=0.95, SI=0.93,
                SK=0.86, TH=0.80, TN=0.73, TR=0.86, TZ=0.53, UG=0.55, US=0.93, VE=0.70, VN=0.73, ZA=0.72, ZM=0.57, ZW=0.55)
HDI_SOURCE = ('UNDP Human Development Report 2023/24 (HDI 2022 values), transcribed from memory, rounded to 2 decimals, UNVERIFIED '
              '(hdr.undp.org unreachable from the build sandbox); band: high >= 0.80, middle 0.70-0.79, low < 0.70; '
              'PR, TW, GF, IO, TC have no UNDP value')
SAMPLE_FILTER = ('body_site_class == primary; not qc_non_metagenome / qc_synthetic / qc_rna / qc_predicted_ecological / '
                 'qc_low_depth / qc_no_genus_assigned')
QC_FLAGS = ('qc_non_metagenome', 'qc_synthetic', 'qc_rna', 'qc_predicted_ecological', 'qc_low_depth', 'qc_no_genus_assigned')


def hdi_band(h):
    if h is None or (isinstance(h, float) and np.isnan(h)):
        return None
    return 'high' if h >= 0.80 else ('low' if h < 0.70 else 'middle')


def analysis_samples(summary: pd.DataFrame) -> pd.DataFrame:
    """The atlas sample set: primary gut samples that pass every Sandpiper QC flag we use (see SAMPLE_FILTER)."""
    m = summary.body_site_class.eq('primary')
    for f in QC_FLAGS:
        if f in summary.columns:
            m &= ~summary[f].fillna(False).astype(bool)
    return summary[m].copy()


def _country_names(isos):
    try:
        import pycountry
    except ImportError:  # pragma: no cover
        return {i: (i, None) for i in isos}
    out = {}
    for iso in isos:
        c = pycountry.countries.get(alpha_2=iso)
        out[iso] = ((getattr(c, 'common_name', None) or c.name), c.numeric) if c else (iso, None)
    return out


def _lineage_part(lineage, prefix):
    if not isinstance(lineage, str):
        return None
    for x in lineage.split('; '):
        if x.startswith(prefix):
            return x
    return None


def precompute(genus_long: pd.DataFrame, species_long: pd.DataFrame, summary: pd.DataFrame, wide: pd.DataFrame, out_dir,
               n_species: int = 500, presence: float = PRESENCE, species_presence: float = SPECIES_PRESENCE, hdi: dict | None = None,
               topo_ids: set | None = None) -> dict:
    """Write the atlas payload to out_dir and return its meta dict.

    genus_long: sample_key, genus, lineage, relabund;  species_long: sample_key, species, lineage, relabund;
    summary: the Sandpiper per-sample summary (sample_key, study_accession, body_site_class, qc_*, age_category, ...);
    wide: package gut_sample_metadata_wide (sample_key, country, ...).
    """
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    hdi = HDI_2022 if hdi is None else hdi
    S = analysis_samples(summary).merge(wide[['sample_key', 'country']].drop_duplicates('sample_key'), on='sample_key', how='left').reset_index(drop=True)
    S['sidx'] = np.arange(len(S), dtype=np.int32)
    N = len(S)
    countries = pd.Index(sorted(S.country.dropna().unique()))
    studies = pd.Index(sorted(S.study_accession.unique()))
    S['cidx'] = countries.get_indexer(S.country.fillna('__')).astype(np.int32)
    S['stidx'] = studies.get_indexer(S.study_accession).astype(np.int32)
    key2idx = pd.Series(S.sidx.values, index=S.sample_key.values)

    g = genus_long[genus_long.sample_key.isin(set(S.sample_key)) & (genus_long.genus != 'unassigned_at_genus')]
    gen_names = pd.Index(sorted(g.genus.unique()))
    G = pd.DataFrame(dict(s=key2idx.reindex(g.sample_key.values).values.astype(np.int32), g=gen_names.get_indexer(g.genus.values).astype(np.int32), ra=g.relabund.values.astype(np.float32)))
    lineage_g = g.drop_duplicates('genus').set_index('genus').lineage.reindex(gen_names)
    del g

    sp = species_long[species_long.sample_key.isin(set(S.sample_key)) & (species_long.species != 'unassigned_at_species')]
    sp_prev = sp.groupby('species').sample_key.nunique().sort_values(ascending=False)
    top_sp = pd.Index(sorted(sp_prev.index[:n_species]))
    sp = sp[sp.species.isin(set(top_sp))]
    lineage_s = sp.drop_duplicates('species').set_index('species').lineage.reindex(top_sp)
    Dsp = pd.DataFrame(dict(s=key2idx.reindex(sp.sample_key.values).values.astype(np.int32), t=top_sp.get_indexer(sp.species.values).astype(np.int32), ra=sp.relabund.values.astype(np.float32)))
    del sp

    n_country = S[S.cidx >= 0].groupby('cidx').size().reindex(range(len(countries)), fill_value=0)
    n_study = S.groupby('stidx').size().reindex(range(len(studies)), fill_value=0)
    nstud_country = S[S.cidx >= 0].groupby('cidx').study_accession.nunique().reindex(range(len(countries)), fill_value=0)

    def agg(df, thr):
        df = df.assign(c=S.cidx.values[df.s.values], st=S.stidx.values[df.s.values], p=(df.ra >= thr).astype(np.int32))
        tc = df[df.c >= 0].groupby(['t', 'c']).agg(n=('p', 'sum'), sra=('ra', 'sum')).reset_index()
        ts = df.groupby(['t', 'st']).agg(n=('p', 'sum'), sra=('ra', 'sum')).reset_index()
        tot = df.groupby('t').agg(n=('p', 'sum'), sra=('ra', 'sum'))
        return tc[tc.n > 0], ts[ts.n > 0], tot

    taxa, sizes, ranks_n = [], {}, {}
    for r in RANKS:
        if r == 'species':
            names, D, lin, thr = top_sp, Dsp, lineage_s, species_presence
        elif r == 'genus':
            names, D, lin, thr = gen_names, G.rename(columns={'g': 't'}), lineage_g, presence
        else:
            rn = np.array([_lineage_part(l, PREFIX[r]) for l in lineage_g.values], dtype=object)
            names = pd.Index(sorted({x for x in rn if x}))
            g2t = names.get_indexer(rn)
            D = G.assign(t=g2t[G.g.values]); D = D[D.t >= 0].groupby(['s', 't'], as_index=False).ra.sum()
            lin = pd.Series(index=names, dtype=object)
            for l, n in zip(lineage_g.values, rn):
                if n and not isinstance(lin[n], str):
                    parts = l.split('; '); lin[n] = '; '.join(parts[:parts.index(n) + 1])
            thr = presence
        tc, ts, tot = agg(D, thr)
        tc_g = {k: v for k, v in tc.groupby('t')}; ts_g = {k: v for k, v in ts.groupby('t')}
        nstud_present = ts.groupby('t').size()
        buf = []
        ri = RANKS.index(r)
        for i, name in enumerate(names):
            a = tc_g.get(i); b = ts_g.get(i)
            ca = np.zeros((0, 3), dtype=np.uint32) if a is None else np.column_stack([a.c.values, a.n.values, np.round(a.sra.values / n_country.values[a.c.values] * 1e6)]).astype(np.uint32)
            sa = np.zeros((0, 3), dtype=np.uint32) if b is None else np.column_stack([b.st.values, b.n.values, np.round(b.sra.values / n_study.values[b.st.values] * 1e6)]).astype(np.uint32)
            buf += [np.array([len(ca), len(sa)], dtype=np.uint32), ca.ravel(), sa.ravel()]
            t = tot.loc[i] if i in tot.index else None
            parent = _lineage_part(lin[name], PREFIX[RANKS[ri - 1]]) if ri else None
            taxa.append(dict(id=f'{r[0]}:{i}', name=name, rank=r, parent=parent, lineage=lin[name] if isinstance(lin[name], str) else None,
                             n=int(t.n) if t is not None else 0, prev=round(float(t.n) / N, 5) if t is not None else 0.0,
                             mean=round(float(t.sra) / N, 7) if t is not None else 0.0, nstud=int(nstud_present.get(i, 0))))
        arr = np.concatenate(buf).astype('<u4') if buf else np.zeros(0, dtype='<u4')
        p = out_dir / f'matrix_{r}.bin'; arr.tofile(p); sizes[r] = p.stat().st_size; ranks_n[r] = len(names)

    cinfo = _country_names(list(countries))
    cn = []
    for i, iso in enumerate(countries):
        name, num = cinfo[iso]
        h = hdi.get(iso)
        d = dict(i=i, iso2=iso, name=name, num=num, in_map=(num in topo_ids) if topo_ids is not None else (iso not in POINT_COUNTRIES),
                 n=int(n_country[i]), nstud=int(nstud_country[i]), hdi=h, band=hdi_band(h))
        if iso in POINT_COUNTRIES:
            d['ll'] = list(POINT_COUNTRIES[iso])
        cn.append(d)
    st_age = S.groupby(['stidx', 'age_category']).size().unstack(fill_value=0).reindex(columns=AGE_CATS, fill_value=0) if 'age_category' in S else None
    st_c = S[S.cidx >= 0].groupby('stidx').country.agg(lambda x: x.value_counts().index[:3].tolist())
    st_stats = S.groupby('stidx').agg(rich=('richness_genus', 'median'), depth=('root_coverage_sum', 'median')) if 'richness_genus' in S else None
    sj = []
    for i, acc in enumerate(studies):
        d = dict(i=i, acc=acc, n=int(n_study[i]), countries=st_c.get(i, []),
                 ages=[int(x) for x in st_age.loc[i].values] if st_age is not None and i in st_age.index else [0] * len(AGE_CATS))
        if st_stats is not None:
            d['rich'] = float(st_stats.loc[i, 'rich']); d['depth'] = float(st_stats.loc[i, 'depth'])
        sj.append(d)
    meta = dict(n_samples=N, n_studies=len(studies), n_countries=len(countries), n_samples_with_country=int((S.cidx >= 0).sum()),
                presence_threshold=presence, species_threshold=species_presence, min_country_samples=MIN_COUNTRY_SAMPLES, ranks=RANKS,
                age_categories=AGE_CATS, taxonomy='GTDB R232 (Sandpiper 2.0.0, Zenodo 20419175)', n_taxa=len(taxa), ranks_n=ranks_n,
                payload_bytes=int(sum(sizes.values())), format=__doc__.split('Payload format')[1].strip(), hdi_source=HDI_SOURCE, sample_filter=SAMPLE_FILTER)
    (out_dir / 'taxa.json').write_text(json.dumps(dict(meta=meta, taxa=taxa), separators=(',', ':')))
    (out_dir / 'countries.json').write_text(json.dumps(cn, separators=(',', ':')))
    (out_dir / 'studies.json').write_text(json.dumps(sj, separators=(',', ':'), ensure_ascii=False))
    pd.DataFrame([dict(iso2=d['iso2'], country=d['name'], hdi_2022=d['hdi'], band=d['band'], n_samples=d['n'], n_studies=d['nstud']) for d in cn]).to_csv(out_dir / 'country_hdi.csv', index=False)
    meta['payload_bytes_total'] = int(sum(p.stat().st_size for p in out_dir.iterdir() if p.is_file()))
    (out_dir / 'taxa.json').write_text(json.dumps(dict(meta=meta, taxa=taxa), separators=(',', ':')))
    return meta


def attach_study_titles(data_dir, studies_df: pd.DataFrame):
    """Add study titles / package n_samples to studies.json from gut_studies (done at site-build time)."""
    p = Path(data_dir) / 'studies.json'
    sj = json.loads(p.read_text())
    t = studies_df.drop_duplicates('study_accession').set_index('study_accession')
    for d in sj:
        if d['acc'] in t.index:
            r = t.loc[d['acc']]
            d['title'] = str(r.get('study_title_u') or r.get('study_title') or '')[:160]
            d['n_pkg'] = int(r['n_samples']) if pd.notna(r.get('n_samples')) else None
    p.write_text(json.dumps(sj, separators=(',', ':'), ensure_ascii=False))


def build(env, render, ctx, out_dir):
    """Render atlas/index.html and atlas/observations.html; copy the precomputed payload to data/atlas/.

    ctx keys: atlas_data_dir (precomputed payload incl. obs/ CSVs+PNGs and observations.json), stats (site stats dict),
    gut_studies (optional DataFrame to attach titles).  Returns the list of written page paths.
    """
    out_dir = Path(out_dir)
    src = Path(ctx['atlas_data_dir'])
    dst = out_dir / 'data' / 'atlas'
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    if ctx.get('gut_studies') is not None:
        attach_study_titles(dst, ctx['gut_studies'])
    taxa_meta = json.loads((dst / 'taxa.json').read_text())['meta']
    obs = json.loads((dst / 'observations.json').read_text()) if (dst / 'observations.json').exists() else dict(meta={}, cards=[])
    for c in obs['cards']:
        c['figure_href'] = f"../data/atlas/obs/{c['figure']}"
        c['csv_href'] = f"../data/atlas/obs/{c['csv']}"
    (out_dir / 'atlas').mkdir(parents=True, exist_ok=True)
    payload_mb = round(taxa_meta.get('payload_bytes_total', 0) / 1e6, 1)
    render('atlas.html', 'atlas/index.html', '../', nav='atlas', meta=taxa_meta, payload_mb=payload_mb, n_obs=len(obs['cards']), stats=ctx.get('stats', {}),
           crumbs=[dict(label='Home', href='../index.html'), dict(label='Atlas')])
    render('observations.html', 'atlas/observations.html', '../', nav='atlas', meta=taxa_meta, obs_meta=obs.get('meta', {}), cards=obs['cards'], stats=ctx.get('stats', {}),
           crumbs=[dict(label='Home', href='../index.html'), dict(label='Atlas', href='index.html'), dict(label='Observations')])
    return ['atlas/index.html', 'atlas/observations.html']

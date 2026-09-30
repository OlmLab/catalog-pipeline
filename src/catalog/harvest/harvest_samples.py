"""Harvest full sample attribute sets: ENA sample XML (batches of 100) then NCBI BioSample efetch for misses.
Writes sample_attributes_partNN.parquet every 10k samples plus harvest_progress.json.
"""
# --- microbiome_repo-pipeline repo layout shim (added 2026-09-26; original ran flat from one cwd) ---
import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__)) if "__file__" in globals() else _os.getcwd()
for _p in (_here, _os.path.join(_here, "..", "..")):
    _p = _os.path.abspath(_p)
    if _p not in _sys.path:
        _sys.path.insert(0, _p)
try:
    from catalog.models import resolve_model, set_host  # registers src/catalog/<stage>/ dirs on sys.path
except ImportError:  # flat-workspace mode (files copied side by side): models.py must sit alongside
    from models import resolve_model, set_host
set_host(globals().get("host"))  # kernel `host` is a frame global, not builtins (R1-01)
def _prompt_path(name):
    """cwd copy first (leaf-worker convention), else the packaged prompt under src/catalog/prompts/."""
    for _c in (name, _os.path.join("pilot_prompts", name), _os.path.join(_here, "..", "prompts", name)):
        if _os.path.exists(_c):
            return _c
    return name
# ---------------------------------------------------------------------------------------------
import sys, os, re, json, time
# (sys.path handled by the repo layout shim above)
import pandas as pd
import xml.etree.ElementTree as ET
import harvest_lib as HL

ENA_URL = "https://www.ebi.ac.uk/ena/browser/api/xml/"
PART_SIZE = 10000
BATCH = 100

def norm_key(k):
    return re.sub(r'[^a-z0-9]+', '_', str(k).lower()).strip('_')

def parse_ena(body):
    """Return (rows, accessions_seen)."""
    rows, seen = [], set()
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return rows, seen
    for s in root.iter('SAMPLE'):
        acc = s.get('accession')
        if not acc:
            pid = s.findtext('IDENTIFIERS/PRIMARY_ID')
            acc = pid
        if not acc:
            continue
        seen.add(acc)
        def add(k, v, u=None):
            if v is None: return
            v = str(v).strip()
            if not v: return
            rows.append((acc, k, norm_key(k), v, u, 'ena_sample_xml'))
        add('alias', s.get('alias'))
        add('center_name', s.get('center_name'))
        add('TITLE', s.findtext('TITLE'))
        add('DESCRIPTION', s.findtext('DESCRIPTION'))
        for tag in ['TAXON_ID', 'SCIENTIFIC_NAME', 'COMMON_NAME', 'ANONYMIZED_NAME', 'INDIVIDUAL_NAME']:
            add('SAMPLE_NAME.' + tag, s.findtext('SAMPLE_NAME/' + tag))
        for idn in s.findall('IDENTIFIERS/SUBMITTER_ID'):
            add('SUBMITTER_ID', idn.text)
        for idn in s.findall('IDENTIFIERS/SECONDARY_ID'):
            add('SECONDARY_ID', idn.text)
        for a in s.iter('SAMPLE_ATTRIBUTE'):
            add(a.findtext('TAG'), a.findtext('VALUE'), a.findtext('UNITS'))
    return rows, seen

def parse_ncbi(text):
    rows, seen = [], set()
    try:
        root = ET.fromstring(text.encode('utf-8') if isinstance(text, str) else text)
    except ET.ParseError:
        return rows, seen
    for b in root.iter('BioSample'):
        acc = b.get('accession')
        if not acc:
            continue
        seen.add(acc)
        def add(k, v, u=None):
            if v is None: return
            v = str(v).strip()
            if not v: return
            rows.append((acc, k, norm_key(k), v, u, 'ncbi_biosample'))
        for idn in b.findall('Ids/Id'):
            db = idn.get('db') or idn.get('db_label') or 'Id'
            add('Id.' + db, idn.text)
        add('TITLE', b.findtext('Description/Title'))
        add('DESCRIPTION', ' '.join(p.text or '' for p in b.findall('Description/Comment/Paragraph')).strip() or None)
        org = b.find('Description/Organism')
        if org is not None:
            add('TAXON_ID', org.get('taxonomy_id'))
            add('SCIENTIFIC_NAME', org.get('taxonomy_name') or org.findtext('OrganismName'))
        for a in b.findall('Attributes/Attribute'):
            k = a.get('harmonized_name') or a.get('attribute_name')
            add(k, a.text, a.get('unit'))
            if a.get('attribute_name') and a.get('harmonized_name') and a.get('attribute_name') != a.get('harmonized_name'):
                rows.append((acc, a.get('attribute_name'), norm_key(a.get('attribute_name')), str(a.text or '').strip(), a.get('unit'), 'ncbi_biosample_raw'))
        for m in b.findall('Models/Model'):
            add('Model', m.text)
        add('Package', b.findtext('Package'))
    return rows, seen

COLS = ['sample_key', 'attr_key', 'attr_key_norm', 'attr_value', 'attr_units', 'source']

def main():
    samples = pd.read_parquet('samples.parquet')
    keys = list(samples.sample_key)
    prog = {'done_parts': [], 'missing_ena': [], 'ena_batches_err': 0, 'ena_batches': 0}
    if os.path.exists('harvest_progress.json'):
        prog = json.load(open('harvest_progress.json'))
    n_parts = (len(keys) + PART_SIZE - 1) // PART_SIZE
    for pi in range(n_parts):
        if pi in prog['done_parts']:
            continue
        chunk = keys[pi*PART_SIZE:(pi+1)*PART_SIZE]
        urls = [ENA_URL + ",".join(chunk[i:i+BATCH]) for i in range(0, len(chunk), BATCH)]
        t0 = time.time()
        res = HL.fetch_many(urls, purpose='sample_xml_harvest', workers=6)
        rows, seen = [], set()
        for u, r in res.items():
            prog['ena_batches'] += 1
            if r.get('ok') and r.get('body'):
                rr, ss = parse_ena(r['body'])
                rows += rr; seen |= ss
            else:
                prog['ena_batches_err'] += 1
        missing = [k for k in chunk if k not in seen]
        prog['missing_ena'] += missing
        df = pd.DataFrame(rows, columns=COLS)
        df.to_parquet(f'sample_attributes_part{pi:02d}.parquet', index=False)
        prog['done_parts'].append(pi)
        json.dump(prog, open('harvest_progress.json', 'w'))
        print(f'part {pi:02d}: {len(chunk)} samples, {len(seen)} found, {len(missing)} missing, {len(df)} rows, {time.time()-t0:.0f}s', flush=True)
    # NCBI pass for misses
    missing = sorted(set(prog['missing_ena']))
    print('ENA missing total', len(missing), flush=True)
    if missing and not prog.get('ncbi_done'):
        rows, seen = [], set()
        for i, txt in enumerate(HL.efetch('biosample', missing, purpose='biosample_efetch_misses', batch=200)):
            if txt:
                rr, ss = parse_ncbi(txt)
                rows += rr; seen |= ss
            if i % 20 == 0:
                print(f'  ncbi batch {i}, rows {len(rows)}', flush=True)
        df = pd.DataFrame(rows, columns=COLS)
        df.to_parquet('sample_attributes_ncbi.parquet', index=False)
        prog['ncbi_found'] = len(seen)
        prog['still_missing'] = [k for k in missing if k not in seen]
        prog['ncbi_done'] = True
        json.dump(prog, open('harvest_progress.json', 'w'))
        print('NCBI found', len(seen), 'still missing', len(prog['still_missing']), flush=True)
    print('DONE', flush=True)

if __name__ == '__main__':
    main()

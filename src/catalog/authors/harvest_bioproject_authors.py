"""Fetch NCBI BioProject XML for all catalog studies; parse publications, organisations, submitter.
Writes bioproject_records.parquet (checkpointed every ~2,000 studies) + bioproject_fetch_log.json."""
import sys, os, json, time, re
sys.path.append(os.getcwd())
# --- microbiome_repo-pipeline shim (2026-09-26, R3-4): harvest_lib lives in src/catalog/harvest/ (cache dir via CATALOG_CACHE_DIR) ---
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "harvest"))
import pandas as pd
import xml.etree.ElementTree as ET
import harvest_lib as HL

studies = pd.read_parquet(sys.argv[1])
acc = studies.study_accession.tolist()
ESB = 100   # accessions per esearch
log = {'esearch_calls': 0, 'esearch_fail': 0, 'efetch_calls': 0, 'efetch_fail': 0,
       'accessions_queried': 0, 'uids_found': 0, 'records_parsed': 0, 'started': time.time()}
records = {}   # accession -> record


def txt(e, path):
    x = e.find(path)
    return (x.text or '').strip() if x is not None and x.text else None


def parse_record(ds):
    rec = {'uid': ds.get('uid')}
    aid = ds.find('./Project/ProjectID/ArchiveID')
    rec['accession'] = aid.get('accession') if aid is not None else None
    rec['archive'] = aid.get('archive') if aid is not None else None
    # secondary/center IDs
    cid = ds.find('./Project/ProjectID/CenterID')
    rec['center_id_center'] = cid.get('center') if cid is not None else None
    rec['center_id'] = (cid.text or '').strip() if cid is not None and cid.text else None
    rec['title'] = txt(ds, './Project/ProjectDescr/Title')
    rec['name'] = txt(ds, './Project/ProjectDescr/Name')
    pubs = []
    for p in ds.findall('./Project/ProjectDescr/Publication'):
        pub = {'id': p.get('id'), 'date': p.get('date'), 'status': p.get('status'),
               'db_type': txt(p, './DbType'), 'reference': txt(p, './Reference'),
               'title': txt(p, './StructuredCitation/Title'),
               'journal': txt(p, './StructuredCitation/Journal/JournalTitle'),
               'year': txt(p, './StructuredCitation/Journal/Year')}
        authors = []
        for a in p.findall('./StructuredCitation/AuthorSet/Author'):
            authors.append({'first': txt(a, './Name/First'), 'last': txt(a, './Name/Last'),
                            'middle': txt(a, './Name/Middle'), 'consortium': txt(a, './Consortium')})
        pub['authors'] = authors
        pubs.append(pub)
    rec['publications'] = json.dumps(pubs)
    rec['n_publications'] = len(pubs)
    rec['publication_pmids'] = ';'.join(p['id'] for p in pubs if p['id'] and (p['db_type'] in (None, 'ePubmed', 'ePMC') or re.fullmatch(r'\d+', p['id'])))
    grants = []
    for g in ds.findall('./Project/ProjectDescr/Grant'):
        grants.append({'id': g.get('GrantId'), 'title': txt(g, './Title'), 'agency': txt(g, './Agency'),
                       'agency_abbr': (g.find('./Agency').get('abbr') if g.find('./Agency') is not None else None)})
    rec['grants'] = json.dumps(grants)
    links = []
    for l in ds.findall('./Project/ProjectDescr/ExternalLink'):
        links.append({'label': l.get('label'), 'category': l.get('category'),
                      'url': txt(l, './URL'), 'db': txt(l, './dbXREF/Db'), 'id': txt(l, './dbXREF/ID')})
    rec['external_links'] = json.dumps(links)
    orgs = []
    for o in ds.findall('./Submission/Description/Organization'):
        orgs.append({'name': txt(o, './Name'), 'abbr': (o.find('./Name').get('abbr') if o.find('./Name') is not None else None),
                     'role': o.get('role'), 'type': o.get('type'), 'url': o.get('url'),
                     'contact': ';'.join(filter(None, [txt(c, './Name/First') and (txt(c, './Name/First') + ' ' + (txt(c, './Name/Last') or '')) for c in o.findall('./Contact')]))})
    rec['organizations'] = json.dumps(orgs)
    rec['organization_names'] = ';'.join(o['name'] for o in orgs if o['name'])
    rec['submitter_owner'] = ';'.join(o['name'] for o in orgs if o['name'] and o.get('role') == 'owner') or None
    sub = ds.find('./Submission')
    rec['submitted'] = sub.get('submitted') if sub is not None else None
    rec['last_update'] = sub.get('last_update') if sub is not None else None
    rec['submission_id'] = sub.get('submission_id') if sub is not None else None
    rec['submission_access'] = txt(ds, './Submission/Description/Access')
    return rec


def flush(final=False):
    df = pd.DataFrame.from_dict(records, orient='index').reset_index(drop=True)
    df.to_parquet('bioproject_records.parquet', index=False)
    log['elapsed_s'] = round(time.time() - log['started'])
    log['records_parsed'] = len(records)
    json.dump(log, open('bioproject_fetch_log.json', 'w'), indent=1)
    print(f"[flush] {len(records)} records, queried {log['accessions_queried']}, {log['elapsed_s']}s", flush=True)


next_ckpt = 2000
for i in range(0, len(acc), ESB):
    chunk = acc[i:i + ESB]
    term = ' OR '.join(f'{a}[PRJA]' for a in chunk)
    r = HL.esearch('bioproject', term, retmax=ESB * 3, purpose='authors_bioproject_esearch')
    log['esearch_calls'] += 1
    log['accessions_queried'] += len(chunk)
    if not r or 'esearchresult' not in r:
        log['esearch_fail'] += 1
        continue
    ids = r['esearchresult'].get('idlist', [])
    log['uids_found'] += len(ids)
    for t in HL.efetch('bioproject', ids, purpose='authors_bioproject_efetch', batch=200):
        log['efetch_calls'] += 1
        if not t:
            log['efetch_fail'] += 1
            continue
        try:
            root = ET.fromstring(t)
        except ET.ParseError:
            log['efetch_fail'] += 1
            continue
        for ds in root.findall('./DocumentSummary'):
            try:
                rec = parse_record(ds)
            except Exception as ex:
                log.setdefault('parse_errors', 0)
                log['parse_errors'] += 1
                continue
            if rec['accession']:
                records[rec['accession']] = rec
    if log['accessions_queried'] >= next_ckpt:
        flush(); next_ckpt += 2000
flush(final=True)
print('DONE', flush=True)

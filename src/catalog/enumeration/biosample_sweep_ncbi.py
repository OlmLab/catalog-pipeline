"""
BioSample-attribute sweep, NCBI side. esearch (usehistory) -> efetch full XML in batches of 500 via
WebEnv/query_key paging (retstart is only limited to 10k without history). Parses each BioSample
into a flat row: accession, sra_sample (SRS from Ids), organism, tax_id, title, description,
package, attributes (json of harmonized_name->value), plus the convenience fields the infant rule
needs. All HTTP via harvest_lib.
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
import sys, json, time
from pathlib import Path
import pandas as pd
from lxml import etree
# (sys.path handled by the repo layout shim above)
import harvest_lib as HL

OUT = Path("ncbi_samples"); OUT.mkdir(exist_ok=True)
TERMS = ('(infant[All Fields] OR neonate[All Fields] OR neonatal[All Fields] OR newborn[All Fields] OR '
         'preterm[All Fields] OR premature[All Fields] OR toddler[All Fields] OR meconium[All Fields] OR '
         'NICU[All Fields] OR "months old"[All Fields] OR "weeks old"[All Fields] OR "days old"[All Fields] OR '
         '"month old"[All Fields] OR "week old"[All Fields] OR "day old"[All Fields])')
GUT = ('(metagenome[All Fields] OR stool[All Fields] OR feces[All Fields] OR fecal[All Fields] OR '
       'faeces[All Fields] OR gut[All Fields] OR microbiome[All Fields] OR microbiota[All Fields] OR meconium[All Fields])')
SRA = 'biosample_sra[Filter]'
QUERIES = {
    "n1_hs_terms": f'"Homo sapiens"[Organism] AND {TERMS} AND {SRA}',
    "n2_meta_terms": f'metagenome[Organism] AND {TERMS} AND {SRA}',
    "n3_meta_hostage": f'host_age[Attribute Name] AND metagenome[Organism] AND {SRA}',
    "n4_hs_hostage": f'host_age[Attribute Name] AND "Homo sapiens"[Organism] AND {SRA}',
    "n5_meta_age_human": f'age[Attribute Name] AND metagenome[Organism] AND "Homo sapiens"[All Fields] AND {SRA}',
    "n6_hs_age_gut": f'age[Attribute Name] AND "Homo sapiens"[Organism] AND {GUT} AND {SRA}',
    "n7_hs_devstage_gut": f'dev_stage[Attribute Name] AND "Homo sapiens"[Organism] AND {GUT} AND {SRA}',
}
BATCH = 500
AGE_KEYS = {"host_age", "age", "host_age_at_collection", "age_at_collection", "infant_age", "age_days",
            "age_in_days", "age_months", "age_in_months", "age_weeks", "age_at_sampling", "sampling_age",
            "host_age_days", "postnatal_age", "chronological_age", "age_group", "age_category", "age_range"}
DEV_KEYS = {"dev_stage", "host_dev_stage", "developmental_stage", "host_life_stage", "life_stage",
            "host_development_stage", "age_class"}
GEST_KEYS = {"host_gest_age", "gestational_age", "gest_age", "ga", "gestational_age_at_birth", "birth_gestational_age"}


def parse_biosamples(xml_text):
    rows = []
    try:
        root = etree.fromstring(xml_text.encode("utf-8"), parser=etree.XMLParser(recover=True, huge_tree=True))
    except Exception as e:
        return rows, f"parse_error {e}"
    if root is None:
        return rows, "empty"
    for bs in root.iter("BioSample"):
        acc = bs.get("accession", "")
        srs = ""
        bioproject = ""
        for i in bs.iter("Id"):
            db = (i.get("db") or "").upper()
            if db == "SRA":
                srs = i.text or ""
        for l in bs.iter("Link"):
            if (l.get("target") or "") == "bioproject":
                bioproject = l.get("label") or l.text or ""
        org = bs.find(".//Organism")
        tax_id = org.get("taxonomy_id", "") if org is not None else ""
        org_name = (org.get("taxonomy_name", "") if org is not None else "") or ""
        title_el = bs.find(".//Description/Title")
        title = (title_el.text or "") if title_el is not None else ""
        para = " ".join((p.text or "") for p in bs.findall(".//Description/Comment/Paragraph"))
        pkg_el = bs.find("Package")
        package = (pkg_el.text or "") if pkg_el is not None else ""
        attrs = {}
        raw_attrs = {}
        for a in bs.iter("Attribute"):
            hn = (a.get("harmonized_name") or a.get("attribute_name") or "").strip().lower().replace(" ", "_")
            an = (a.get("attribute_name") or "").strip()
            v = (a.text or "").strip()
            if hn:
                attrs[hn] = v
            if an:
                raw_attrs[an] = v
        def pick(keys):
            hits = [(k, v) for k, v in attrs.items() if k in keys and v and v.lower() not in
                    {"missing", "not collected", "not applicable", "na", "n/a", "none", "unknown", "not provided", "restricted access"}]
            return hits[0][1] if hits else "", hits[0][0] if hits else ""
        age, age_key = pick(AGE_KEYS)
        dev, dev_key = pick(DEV_KEYS)
        gest, gest_key = pick(GEST_KEYS)
        rows.append({
            "biosample": acc, "srs": srs, "bioproject": bioproject, "tax_id": tax_id, "organism": org_name,
            "title": title, "description": para, "package": package,
            "host": attrs.get("host", ""), "host_taxid": attrs.get("host_taxid", attrs.get("host_tax_id", "")),
            "host_body_site": attrs.get("host_body_site", attrs.get("body_site", "")),
            "isolation_source": attrs.get("isolation_source", ""), "env_medium": attrs.get("env_medium", ""),
            "collection_date": attrs.get("collection_date", ""),
            "age": age, "age_key": age_key, "dev_stage": dev, "dev_key": dev_key, "gest_age": gest, "gest_key": gest_key,
            "attributes_json": json.dumps(attrs, ensure_ascii=False),
        })
    return rows, ""


def run_query(name, term):
    out = OUT / f"{name}.parquet"
    if out.exists():
        return len(pd.read_parquet(out, columns=["biosample"]))
    d = HL.esearch("biosample", term, retmax=0, usehistory=True, purpose="biosample_sweep_ncbi_esearch")
    es = d["esearchresult"]
    count, webenv, qk = int(es["count"]), es["webenv"], es["querykey"]
    rows, errs, t0 = [], [], time.time()
    for start in range(0, count, BATCH):
        url = (f"{HL.EUTILS}/efetch.fcgi?db=biosample&query_key={qk}&WebEnv={webenv}"
               f"&retstart={start}&retmax={BATCH}&rettype=full&retmode=xml" + HL._ncbi_suffix())
        txt = HL.fetch_text(url, purpose="biosample_sweep_ncbi_efetch")
        if not isinstance(txt, str) or "<BioSample" not in txt:
            errs.append((start, str(txt)[:120]))
            continue
        got, err = parse_biosamples(txt)
        if err:
            errs.append((start, err))
        for r in got:
            r["ncbi_query"] = name
        rows.extend(got)
        if (start // BATCH) % 20 == 0:
            print(f"  {name} {start}/{count} rows={len(rows)} {time.time()-t0:.0f}s", flush=True)
    df = pd.DataFrame(rows)
    df.to_parquet(out, index=False)
    json.dump({"count": count, "rows": len(df), "errors": errs}, open(OUT / f"{name}.meta.json", "w"))
    print(f"{name}\texpected={count}\tgot={len(df)}\terrors={len(errs)}\t{time.time()-t0:.0f}s", flush=True)
    return len(df)


if __name__ == "__main__":
    names = sys.argv[1:] or list(QUERIES)
    tot = 0
    for n in names:
        try:
            tot += run_query(n, QUERIES[n])
        except Exception as e:
            print(f"{n}\tERROR\t{type(e).__name__}: {str(e)[:200]}", flush=True)
    print("TOTAL_ROWS", tot)

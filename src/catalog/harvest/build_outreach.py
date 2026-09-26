"""
build_outreach.py -- submitter-outreach pack for catalog_status == human_review studies.

Sources, in order, for every study:
  1. ENA project XML  https://www.ebi.ac.uk/ena/browser/api/xml/<PRJ>
       -> center_name, broker_name, title, PUBMED xrefs
  2. NCBI BioProject (eutils esearch+efetch)  -> submitting organization, publication PMIDs
  3. Papers: paper_study_links.parquet, catalog linked_pmids, PMC ids quoted in the review note,
     ENA/NCBI PUBMED xrefs, Europe PMC full-text search for the accession
  4. Europe PMC full-text XML (open access only) -> corresponding author(s), affiliation, email
No LLM. Nothing is inferred: contact fields are copied from the XML or left empty.
"""
# --- catalog-pipeline repo layout shim (added 2026-09-26; original ran flat from one cwd) ---
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
import io
import json
import re
import sys
import time

import pandas as pd
from lxml import etree

# (sys.path handled by the repo layout shim above)
import harvest_lib as HL  # noqa: E402

CATALOG = "catalog_studies.parquet"
LINKS = "paper_study_links.parquet"
MAX_PAPERS_PER_STUDY = 4


def ena_project(acc):
    r = HL.fetch(f"https://www.ebi.ac.uk/ena/browser/api/xml/{acc}", purpose="outreach_ena_xml")
    out = {"ena_center_name": "", "ena_broker_name": "", "ena_title": "", "ena_pubmed": [], "ena_first_public": "",
           "ena_xml_ok": bool(r["ok"])}
    if not r["ok"]:
        return out
    try:
        root = etree.fromstring(r["body"])
    except etree.XMLSyntaxError:
        return out
    p = root.find(".//PROJECT")
    if p is None:
        return out
    out["ena_center_name"] = p.get("center_name", "") or ""
    out["ena_broker_name"] = p.get("broker_name", "") or ""
    out["ena_title"] = (p.findtext("TITLE") or "").strip()
    for x in p.findall(".//XREF_LINK"):
        if (x.findtext("DB") or "").upper() == "PUBMED":
            out["ena_pubmed"] += re.findall(r"\d{6,9}", x.findtext("ID") or "")
    for a in p.findall(".//PROJECT_ATTRIBUTE"):
        if (a.findtext("TAG") or "") == "ENA-FIRST-PUBLIC":
            out["ena_first_public"] = a.findtext("VALUE") or ""
    return out


def ncbi_bioproject(acc):
    out = {"ncbi_organization": "", "ncbi_pubmed": [], "ncbi_ok": False}
    try:
        es = HL.esearch("bioproject", f"{acc}[Project Accession]", retmax=5, purpose="outreach_bp_esearch")
        ids = re.findall(r"<Id>(\d+)</Id>", es or "") if isinstance(es, str) else (es or {}).get("esearchresult", {}).get("idlist", [])
        if not ids:
            return out
        xml = "".join(x or "" for x in HL.efetch("bioproject", ids[:1], rettype="xml", retmode="xml",
                                                 purpose="outreach_bp_efetch"))
        if not xml:
            return out
        root = etree.fromstring(xml.encode() if isinstance(xml, str) else xml)
        out["ncbi_ok"] = True
        org = root.find(".//Submission/Description/Organization/Name")
        if org is not None:
            out["ncbi_organization"] = (org.text or "").strip()
        for pub in root.findall(".//Publication"):
            pid = pub.get("id") or ""
            if re.fullmatch(r"\d{6,9}", pid):
                out["ncbi_pubmed"].append(pid)
            dbt = pub.find(".//DbType")
            if dbt is not None and dbt.text == "ePubmed" and pid.isdigit():
                out["ncbi_pubmed"].append(pid)
        out["ncbi_pubmed"] = sorted(set(out["ncbi_pubmed"]))
    except Exception as e:  # network / parse failure -> recorded, not fatal
        out["ncbi_error"] = str(e)[:120]
    return out


def epmc_accession_papers(acc):
    """Europe PMC papers whose text mentions the accession (core result type)."""
    d = HL.epmc_search(f'"{acc}"', page_size=25, purpose="outreach_epmc_acc")
    rows = []
    for h in (d or {}).get("resultList", {}).get("result", []):
        rows.append({"pmid": h.get("pmid", ""), "pmcid": h.get("pmcid", ""), "doi": h.get("doi", ""),
                     "title": h.get("title", ""), "is_oa": h.get("isOpenAccess", "N") == "Y",
                     "year": h.get("pubYear", ""), "paper_source": "epmc_fulltext_search"})
    return rows


def epmc_lookup(ids, kind):
    """Resolve PMIDs or PMCIDs to core records (pmid, pmcid, title, OA)."""
    rows = []
    ids = [i for i in dict.fromkeys(ids) if i]
    for i in range(0, len(ids), 20):
        b = ids[i:i + 20]
        q = " OR ".join(f"{'EXT_ID' if kind == 'pmid' else 'PMCID'}:{x}" for x in b)
        d = HL.epmc_search(q, page_size=50, purpose="outreach_epmc_ids")
        for h in (d or {}).get("resultList", {}).get("result", []):
            rows.append({"pmid": h.get("pmid", ""), "pmcid": h.get("pmcid", ""), "doi": h.get("doi", ""),
                         "title": h.get("title", ""), "is_oa": h.get("isOpenAccess", "N") == "Y",
                         "year": h.get("pubYear", "")})
    return rows


def _text(el):
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip() if el is not None else ""


def corresp_from_xml(pmcid):
    """Corresponding authors from a JATS full-text XML: names, affiliations, emails present in the XML."""
    r = HL.epmc_fulltext_xml(pmcid, purpose="outreach_epmc_xml")
    out = {"fulltext_ok": False, "corresp": []}
    x = r.get("body") if isinstance(r, dict) else r
    if not (isinstance(r, dict) and r.get("ok")) or not x:
        return out
    try:
        root = etree.fromstring(x if isinstance(x, bytes) else x.encode())
    except etree.XMLSyntaxError:
        return out
    out["fulltext_ok"] = True
    affs = {a.get("id"): _text(a) for a in root.iter("aff") if a.get("id")}
    corresp_notes = {c.get("id"): _text(c) for c in root.iter("corresp")}
    corresp_emails = {cid: sorted(set(_text(e) for e in c.iter("email")))
                      for cid, c in ((c.get("id"), c) for c in root.iter("corresp"))}
    # footnotes such as <fn id=..><p>Corresponding author.</p></fn> referenced by xref ref-type="author-notes"
    for fn in root.iter("fn"):
        if fn.get("id") and re.search(r"correspond", _text(fn), flags=re.I):
            corresp_notes[fn.get("id")] = _text(fn)
            corresp_emails[fn.get("id")] = sorted(set(_text(e) for e in fn.iter("email")))
    for contrib in root.iter("contrib"):
        if contrib.get("contrib-type") not in (None, "author"):
            continue
        rids = [x.get("rid") for x in contrib.findall("xref")]
        is_corr = (contrib.get("corresp") == "yes"
                   or any(x.get("ref-type") == "corresp" for x in contrib.findall("xref"))
                   or any(r in corresp_notes for r in rids)
                   or contrib.find(".//email") is not None)
        if not is_corr:
            continue
        nm = contrib.find("name")
        name = ""
        if nm is not None:
            name = " ".join(t for t in [nm.findtext("given-names") or "", nm.findtext("surname") or ""] if t).strip()
        else:
            name = _text(contrib.find("string-name")) or _text(contrib.find("collab"))
        emails = sorted(set(_text(e) for e in contrib.iter("email")))
        for rid in rids:
            emails += corresp_emails.get(rid, [])
        aff_txt = " ; ".join(affs[r] for r in rids if r in affs)
        if not aff_txt:
            aff_txt = _text(contrib.find("aff"))
        out["corresp"].append({"name": name, "affiliation": aff_txt[:400], "emails": sorted(set(emails)),
                               "corresp_note": " ".join(corresp_notes.get(r, "") for r in rids if r in corresp_notes)[:300]})
    if not out["corresp"] and corresp_notes:
        # no contrib flagged; fall back to the <corresp> note text itself (author name may be inside)
        for cid, txt in corresp_notes.items():
            out["corresp"].append({"name": "", "affiliation": "", "emails": corresp_emails.get(cid, []),
                                   "corresp_note": txt[:300]})
    return out


MISSING_RULES = [
    (r"per-sample age|no age|no ages|age range|ages? (is|are) (not|never) (given|stated|reported)|minimum age|age-?unknown|no minimum",
     "per-sample age (or an age range showing whether subjects <36 months are present)"),
    (r"RNA|16S|amplicon|OTHER|library|assay", "library type confirmation (DNA shotgun vs amplicon/RNA)"),
    (r"subject|paired|sample IDs|sample identifiers|mapping|which patients|per-sample", "sample-to-subject mapping"),
]


def missing_evidence(note):
    note = note or ""
    m = re.search(r"UNRESOLVABLE:\s*(.*)", note, flags=re.S)
    seg = (m.group(1) if m else note).strip()
    fields = [label for rx, label in MISSING_RULES if re.search(rx, seg, flags=re.I)]
    if not fields:
        fields = ["per-sample age (or an age range showing whether subjects <36 months are present)"]
    return seg[:600], "; ".join(dict.fromkeys(fields))


def main():
    cat = pd.read_parquet(CATALOG)
    hr = cat[cat.catalog_status == "human_review"].copy()
    links = pd.read_parquet(LINKS)
    rows, paper_rows, log = [], [], []
    t0 = time.time()
    for i, s in enumerate(hr.itertuples(index=False), 1):
        acc = s.study_accession
        ena = ena_project(acc)
        ncbi = ncbi_bioproject(acc)
        # ---- candidate papers, ranked by how likely the paper's authors are the data owners
        #  tier 0: PMC ids quoted in the human-review note (cohort paper identified by the reviewer), in note order
        #  tier 1: paper_study_links relation == own_data / det_data_availability, not contested
        #  tier 2: ENA / NCBI BioProject PUBMED xrefs; catalog linked_pmids without a relation
        #  tier 3: reused_public_data / contested links (re-analyses; authors are NOT the submitters)
        #  tier 4: Europe PMC full-text search hits for the accession
        tiers = {}
        for k, pmc in enumerate(re.findall(r"PMC\d{5,9}", s.note or "")):
            tiers.setdefault(("pmcid", pmc), (0, k, "review_note_cohort_paper"))
        lk = links[links.study_accession == acc]
        for r in lk.itertuples(index=False):
            pid = str(r.pmid) if pd.notna(r.pmid) else ""
            key = ("pmid", pid) if re.fullmatch(r"\d{6,9}", pid) else ("pmcid", str(r.pmcid))
            rel = r.relation if isinstance(r.relation, str) else "unknown"
            if rel == "own_data" and not bool(r.contested):
                tiers.setdefault(key, (1, 0, "own_data"))
            elif rel in ("reused_public_data",) or bool(r.contested):
                tiers.setdefault(key, (3, 0, f"{rel}{' contested' if bool(r.contested) else ''}"))
            else:
                tiers.setdefault(key, (2, 1, rel))
        for pid in ena["ena_pubmed"] + ncbi["ncbi_pubmed"]:
            tiers.setdefault(("pmid", pid), (2, 0, "archive_pubmed_xref"))
        if isinstance(s.linked_pmids, str) and s.linked_pmids:
            for pid in re.findall(r"\d{6,9}", s.linked_pmids):
                tiers.setdefault(("pmid", pid), (2, 2, "catalog_linked_pmid"))
        papers = {}
        recs = epmc_lookup([k[1] for k in tiers if k[0] == "pmid"], "pmid") + \
               epmc_lookup([k[1] for k in tiers if k[0] == "pmcid"], "pmcid")
        for r in recs:
            t = tiers.get(("pmid", r["pmid"])) or tiers.get(("pmcid", r["pmcid"]))
            if t is None:
                continue
            r["tier"], r["tier_order"], r["paper_relation"] = t
            r["paper_source"] = "catalog_link_or_archive_xref"
            key = r["pmid"] or r["pmcid"]
            if key not in papers or papers[key]["tier"] > r["tier"]:
                papers[key] = r
        for r in epmc_accession_papers(acc):
            r["tier"], r["tier_order"], r["paper_relation"] = 4, 0, "epmc_fulltext_search"
            papers.setdefault(r["pmid"] or r["pmcid"] or r["doi"], r)
        plist = sorted(papers.values(), key=lambda r: (r["tier"], r["tier_order"], not r["is_oa"]))
        plist = plist[:MAX_PAPERS_PER_STUDY]
        # ---- corresponding authors from OA full text
        best = None
        for p in plist:
            c = {"fulltext_ok": False, "corresp": []}
            if p["is_oa"] and p["pmcid"]:
                c = corresp_from_xml(p["pmcid"])
            p["fulltext_ok"] = c["fulltext_ok"]
            p["n_corresp"] = len(c["corresp"])
            paper_rows.append({"study_accession": acc, "pmid": p["pmid"], "pmcid": p["pmcid"], "doi": p["doi"],
                               "paper_title": p["title"], "paper_year": p["year"], "paper_source": p["paper_source"],
                               "paper_relation": p["paper_relation"], "is_oa": p["is_oa"], "fulltext_ok": c["fulltext_ok"], "n_corresp": len(c["corresp"]),
                               "corresponding_author": "", "affiliation": "", "contact_email_if_published": "", "corresp_note": "",
                               "row_type": "paper"})
            for ca in c["corresp"]:
                paper_rows.append({"study_accession": acc, "pmid": p["pmid"], "pmcid": p["pmcid"], "doi": p["doi"],
                                   "paper_title": p["title"], "paper_year": p["year"], "paper_source": p["paper_source"],
                                   "paper_relation": p["paper_relation"], "corresponding_author": ca["name"], "affiliation": ca["affiliation"],
                                   "contact_email_if_published": ";".join(ca["emails"]),
                                   "corresp_note": ca["corresp_note"], "is_oa": p["is_oa"], "fulltext_ok": True,
                                   "n_corresp": len(c["corresp"]), "row_type": "corresponding_author"})
            if c["corresp"] and best is None:
                best = (p, any(ca["emails"] for ca in c["corresp"]), c["corresp"])
        if not plist:
            pass
        seg, fields = missing_evidence(s.note)
        center = ena["ena_center_name"] or ncbi["ncbi_organization"] or (s.center_name if hasattr(s, "center_name") else "")
        row = {"study_accession": acc, "title": ena["ena_title"] or s.study_title, "n_samples": int(s.n_samples) if pd.notna(s.n_samples) else None,
               "missing_field": fields, "missing_evidence": seg,
               "center_name": center, "broker": ena["ena_broker_name"], "ncbi_organization": ncbi["ncbi_organization"],
               "n_papers_found": len(plist), "paper_pmid": "", "paper_pmcid": "", "paper_title": "", "paper_is_oa": "", "paper_relation": "",
               "contact_is_likely_data_owner": "",
               "corresponding_author": "", "affiliation": "", "contact_email_if_published": "", "source_of_contact": "",
               "decision_stage": s.decision_stage, "first_public": ena["ena_first_public"] or str(s.first_public_min)}
        if best:
            p, has_email, cs = best
            row.update({"paper_pmid": p["pmid"], "paper_pmcid": p["pmcid"], "paper_title": p["title"], "paper_is_oa": p["is_oa"],
                        "paper_relation": p["paper_relation"], "contact_is_likely_data_owner": p["tier"] <= 2,
                        "corresponding_author": " | ".join(c["name"] for c in cs if c["name"]),
                        "affiliation": " | ".join(dict.fromkeys(c["affiliation"] for c in cs if c["affiliation"]))[:600],
                        "contact_email_if_published": ";".join(sorted({e for c in cs for e in c["emails"]})),
                        "source_of_contact": f"Europe PMC full-text XML {p['pmcid']} <contrib corresp>/<author-notes>"})
        elif plist:
            p = plist[0]
            row.update({"paper_pmid": p["pmid"], "paper_pmcid": p["pmcid"], "paper_title": p["title"], "paper_is_oa": p["is_oa"],
                        "paper_relation": p["paper_relation"], "contact_is_likely_data_owner": p["tier"] <= 2,
                        "source_of_contact": ("paper found but not open access / no full-text XML -> corresponding author "
                                              "must be read from the publisher page") if not p.get("fulltext_ok") else
                        "OA full text has no corresponding-author markup"})
        else:
            row["source_of_contact"] = ("no paper cites this accession (Europe PMC full-text search + catalog links); "
                                        "contact via ENA/NCBI submitting centre" + (f" ({center})" if center else ""))
        rows.append(row)
        log.append(f"{i:2d} {acc} papers={len(plist)} corresp={'Y' if best else 'N'} email={'Y' if best and best[1] else 'N'} center={center[:40]!r}")
        print(log[-1], flush=True)
    df = pd.DataFrame(rows)
    df.to_csv("outreach_contacts.csv", index=False)
    pd.DataFrame(paper_rows).to_csv("outreach_contacts_all_papers.csv", index=False)
    json.dump({"runtime_s": round(time.time() - t0), "log": log}, open("outreach_build_log.json", "w"), indent=1)
    print(f"{len(df)} studies; with paper {int((df.n_papers_found>0).sum())}; with corresponding author "
          f"{int((df.corresponding_author!='').sum())}; with published email {int((df.contact_email_if_published!='').sum())}; "
          f"{time.time()-t0:.0f}s")
    return df


if __name__ == "__main__":
    main()

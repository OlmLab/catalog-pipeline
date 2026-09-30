"""
Step 8a -- mine dataset accessions out of paper full text.

Why this is mandatory rather than optional: Europe PMC registers a data
cross-reference for only 388 of the 12,859 harvested papers (3.0%), and those
records carry a bare database name with no accession number. The literature
index cannot link papers to data, so the link has to be recovered from the text
itself -- data-availability statements, methods sections, and supplementary
captions.

The fetched full text is not discarded. It is the same corpus the later metadata
extraction stage reads, so every document retrieved here is cached on disk for
reuse rather than re-fetched.
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
import json
import re
import sys
import time
from pathlib import Path

import pandas as pd

# (sys.path handled by the repo layout shim above)
import harvest_lib as HL

# INSDC study/project, plus the non-INSDC repositories we must detect in order to
# tier access correctly (controlled access is a different class from paywalling).
ACC_PATTERNS = {
    "bioproject":  r"\bPRJ(?:NA|EB|DA|DB|CA)\d{3,9}\b",
    "sra_study":   r"\b(?:SRP|ERP|DRP)\d{5,9}\b",
    "sra_sample":  r"\b(?:SRS|ERS|DRS)\d{5,9}\b",
    "sra_run":     r"\b(?:SRR|ERR|DRR)\d{5,9}\b",
    "biosample":   r"\bSAM(?:N|EA|EG|D)\d{5,12}\b",
    "geo":         r"\bGSE\d{3,7}\b",
    "ega":         r"\bEGA[SD]\d{8,13}\b",
    "dbgap":       r"\bphs\d{6}(?:\.v\d+\.p\d+)?\b",
    "gsa":         r"\b(?:CRA|HRA|PRJCA)\d{5,7}\b",
    "mgrast":      r"\bmgp\d{3,6}\b",
    "mgnify":      r"\bMGYS\d{8}\b",
    "figshare_doi": r"\b10\.6084/m9\.figshare\.\d+\b",
    "zenodo_doi":  r"\b10\.5281/zenodo\.\d+\b",
    "dryad_doi":   r"\b10\.5061/dryad\.[a-z0-9]+\b",
}
COMPILED = {k: re.compile(v, re.I) for k, v in ACC_PATTERNS.items()}

# Accession-like strings that are not datasets. PRJNA716514 is the swine project
# the grant text cites; it is a real project, just not ours -- kept here only as a
# reminder that pattern matches are candidates, not links.
TAG_RX = re.compile(r"<[^>]+>")


def strip_xml(x):
    return TAG_RX.sub(" ", x)


def mine(text):
    hits = {}
    for kind, rx in COMPILED.items():
        found = sorted({m.upper() for m in rx.findall(text)})
        if found:
            hits[kind] = found
    return hits


def main(limit=None):
    Path("fulltext").mkdir(exist_ok=True)
    papers = pd.read_parquet("papers_raw.parquet")

    # Free pass first: abstracts often carry the data-availability accession.
    abs_rows = []
    for _, r in papers.iterrows():
        blob = " ".join(str(r.get(c) or "") for c in ("title", "abstractText"))
        h = mine(blob)
        if h:
            abs_rows.append({"paper_id": r["id"], "pmid": r.get("pmid"),
                             "pmcid": r.get("pmcid"), "doi": r.get("doi"),
                             "source": "abstract", "accessions": json.dumps(h)})
    pd.DataFrame(abs_rows).to_parquet("accessions_from_abstract.parquet", index=False)
    print(f"abstract mining: {len(abs_rows):,} of {len(papers):,} papers carry an accession",
          flush=True)

    # Full text for everything Europe PMC will serve.
    ft = papers[(papers.inEPMC == "Y") & papers.pmcid.notna()]
    if limit:
        ft = ft.head(limit)
    print(f"full text to fetch: {len(ft):,}", flush=True)

    rows, t0, nok, nfail = [], time.time(), 0, 0
    for i, (_, r) in enumerate(ft.iterrows(), 1):
        pmcid = r["pmcid"]
        dest = Path("fulltext") / f"{pmcid}.xml"
        try:
            if dest.exists():
                xml = dest.read_text(errors="replace")
            else:
                # harvest_lib.fetch returns a response dict, not text -- the body
                # must be unwrapped and decoded.
                resp = HL.epmc_fulltext_xml(pmcid, purpose="ft_mine")
                xml = (resp["body"].decode("utf8", "replace")
                       if isinstance(resp, dict) and resp.get("ok") and resp.get("body")
                       else None)
                if xml:
                    dest.write_text(xml)
            if not xml:
                nfail += 1
                rows.append({"paper_id": r["id"], "pmcid": pmcid, "doi": r.get("doi"),
                             "source": "fulltext", "status": "empty",
                             "accessions": "{}", "n_chars": 0})
                continue
            nok += 1
            h = mine(strip_xml(xml))
            rows.append({"paper_id": r["id"], "pmcid": pmcid, "doi": r.get("doi"),
                         "source": "fulltext", "status": "ok",
                         "accessions": json.dumps(h), "n_chars": len(xml)})
        except Exception as e:
            nfail += 1
            rows.append({"paper_id": r["id"], "pmcid": pmcid, "doi": r.get("doi"),
                         "source": "fulltext", "status": f"error:{type(e).__name__}",
                         "accessions": "{}", "n_chars": 0})
        if i % 250 == 0:
            pd.DataFrame(rows).to_parquet("accessions_from_fulltext.parquet", index=False)
            print(f"  {i:,}/{len(ft):,} ok={nok} fail={nfail} "
                  f"{(time.time()-t0)/60:.1f}min", flush=True)

    out = pd.DataFrame(rows)
    out.to_parquet("accessions_from_fulltext.parquet", index=False)
    withacc = (out.accessions != "{}").sum()
    print(f"\nfull text retrieved: {nok:,} | failed: {nfail:,}")
    print(f"papers with >=1 accession in full text: {withacc:,} ({withacc/max(len(out),1):.1%})")


if __name__ == "__main__":
    main()

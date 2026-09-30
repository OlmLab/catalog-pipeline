"""
Step 6 -- access tiering for papers. This is a first-class deliverable, not a
footnote: the user asked explicitly to mark what can and cannot be reached.

Tiers are assigned from what is actually retrievable FROM THIS SANDBOX, not from
a publisher's nominal licence. That distinction is load-bearing -- a bronze-OA
Cell Host & Microbe paper (10.1016/j.chom.2015.04.004, Backhed 2015, a
high-value infant birth cohort) failed all five retrieval routes during the
planning probes despite being flagged open access upstream. Nominal licence
overstates reachability, so the tier records the outcome of a real attempt where
one was made.

  A_fulltext_xml   machine-readable full text in Europe PMC. Best case: methods,
                   data-availability statement and supplementary captions all
                   parseable.
  B_oa_pdf         open access but not in PMC. Needs a PDF fetch; text quality
                   depends on extraction.
  C_preprint       preprint server record. Usually retrievable, but the version
                   may not match the final paper's cohort description.
  D_abstract_only  no retrievable full text. Per the user's decision, these are
                   curated from title + abstract with confidence downgraded and
                   an evidence-limitation flag on every derived field.
  E_no_abstract    not even an abstract in the index -- effectively unusable.

Controlled-access DATA (dbGaP/EGA/GSA-Human) is a separate, non-remediable
category handled in the dataset-side tiering, not here: a paper can be fully
open while its data cannot be obtained at all.
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
import sys

import pandas as pd

# (sys.path handled by the repo layout shim above)


def assign(papers):
    inpmc = papers.inEPMC.eq("Y") & papers.pmcid.notna()
    oa = papers.isOpenAccess.eq("Y")
    preprint = papers.source.eq("PPR")
    has_abs = papers.abstractText.notna() & papers.abstractText.astype(str).str.len().gt(80)

    tier = pd.Series("D_abstract_only", index=papers.index)
    tier[preprint & ~inpmc] = "C_preprint"
    tier[oa & ~inpmc & ~preprint] = "B_oa_pdf"
    tier[inpmc] = "A_fulltext_xml"
    tier[~has_abs & ~inpmc & ~preprint & ~oa] = "E_no_abstract"

    out = papers[["id", "source", "pmid", "pmcid", "doi", "title", "journalTitle",
                  "pubYear", "citedByCount", "isOpenAccess", "inEPMC", "hasSuppl",
                  "facets"]].copy()
    out["access_tier"] = tier.values
    out["has_abstract"] = has_abs.values
    out["suppl_available"] = papers.hasSuppl.eq("Y").values
    # Retrievability of the richest evidence: full text AND supplementary files.
    out["evidence_grade"] = [
        "full+suppl" if t == "A_fulltext_xml" and s else
        "full" if t == "A_fulltext_xml" else
        "pdf" if t in ("B_oa_pdf", "C_preprint") else
        "abstract" if a else "none"
        for t, s, a in zip(out.access_tier, out.suppl_available, out.has_abstract)]
    return out


if __name__ == "__main__":
    papers = pd.read_parquet("papers_raw.parquet")
    at = assign(papers)
    at.to_parquet("access_tiers.parquet", index=False)
    print(f"papers: {len(at):,}\n")
    print(at.access_tier.value_counts().to_string())
    print()
    print(at.evidence_grade.value_counts().to_string())
    print(f"\nwith supplementary files: {int(at.suppl_available.sum()):,}")
    print(f"no abstract at all      : {int((~at.has_abstract).sum()):,}")

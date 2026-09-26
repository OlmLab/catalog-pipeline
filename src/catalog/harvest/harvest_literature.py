"""
Step 4 -- literature channel, run as an INDEPENDENT recall complement to the
archive enumeration rather than as the primary frame.

Its job is not to find papers for their own sake. It is to find the studies the
archive frame misses: papers whose data sit in an archive we did not enumerate,
papers whose deposits are typed under a taxon outside the frame, papers with no
deposit at all, and papers behind controlled access. Overlap between this channel
and the archive channel is what makes the capture-recapture coverage estimate in
Step 9 possible, so per-facet novel yield is recorded, not just the union.

Note on query syntax: Europe PMC does not support a trailing wildcard inside a
quoted phrase ("shotgun metagenom*" returns 0 hits), so phrase facets are spelled
out rather than wildcarded.
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
import json
import sys
import time
from pathlib import Path

import pandas as pd

# (sys.path handled by the repo layout shim above)
import harvest_lib as HL

INFANT = ('(infant OR infants OR infancy OR neonate OR neonates OR neonatal OR '
          'newborn OR newborns OR preterm OR premature OR prematurity OR baby OR '
          'babies OR toddler OR toddlers OR weaning OR meconium OR breastfed OR '
          'breastfeeding OR "breast milk" OR "formula-fed" OR colostrum OR NICU OR '
          '"birth cohort" OR "early life" OR "first year of life" OR "first 1000 days" OR '
          '"mother-infant" OR "maternal-infant" OR "necrotizing enterocolitis" OR '
          '"necrotising enterocolitis")')

GUT = ('(gut OR stool OR stools OR fecal OR faecal OR feces OR faeces OR intestinal OR '
       'intestine OR meconium OR "gastrointestinal tract" OR enteric)')

SHOTGUN = ('("shotgun metagenomics" OR "shotgun metagenomic" OR "shotgun metagenome" OR '
           '"metagenomic sequencing" OR "metagenomics sequencing" OR "whole metagenome" OR '
           '"whole-metagenome" OR "whole genome shotgun" OR "whole-genome shotgun" OR '
           '"metagenome-assembled" OR "metagenome assembled" OR "shotgun sequencing" OR '
           'metagenomics OR metagenomic OR metagenome)')

STRAIN = ('("strain-level" OR "strain level" OR "strain transmission" OR '
          '"vertical transmission" OR "strain sharing" OR "metagenome-assembled genome" OR '
          'MAGs OR "single nucleotide variant")')

FACETS = {
    "core_shotgun":        f'(TITLE_ABS:{INFANT}) AND (TITLE_ABS:{GUT}) AND (TITLE_ABS:{SHOTGUN})',
    "shotgun_phrase":      f'(TITLE_ABS:{INFANT}) AND (TITLE_ABS:("shotgun metagenomics" OR "shotgun metagenomic" OR "shotgun metagenome"))',
    "metagenomic_seq":     f'(TITLE_ABS:{INFANT}) AND (TITLE_ABS:"metagenomic sequencing")',
    "meconium":            f'(TITLE_ABS:meconium) AND (TITLE_ABS:{SHOTGUN})',
    "preterm_nicu":        f'(TITLE_ABS:(preterm OR NICU OR "very low birth weight" OR VLBW OR ELBW)) AND (TITLE_ABS:{SHOTGUN}) AND (TITLE_ABS:{GUT})',
    "birth_cohort":        f'(TITLE_ABS:("birth cohort" OR "mother-infant" OR "mother-child")) AND (TITLE_ABS:{SHOTGUN})',
    "breast_milk":         f'(TITLE_ABS:("breast milk" OR breastmilk OR colostrum OR "human milk")) AND (TITLE_ABS:{SHOTGUN}) AND (TITLE_ABS:{INFANT})',
    "strain_transmission": f'(TITLE_ABS:{INFANT}) AND (TITLE_ABS:{STRAIN}) AND (TITLE_ABS:{GUT})',
    "nec":                 f'(TITLE_ABS:("necrotizing enterocolitis" OR "necrotising enterocolitis")) AND (TITLE_ABS:{SHOTGUN})',
    "delivery_mode":       f'(TITLE_ABS:(caesarean OR cesarean OR "c-section" OR "delivery mode" OR "mode of delivery")) AND (TITLE_ABS:{SHOTGUN}) AND (TITLE_ABS:{GUT})',
    "bifido_hmo":          f'(TITLE_ABS:("Bifidobacterium infantis" OR "B. infantis" OR "human milk oligosaccharides" OR "human milk oligosaccharide" OR HMO)) AND (TITLE_ABS:{SHOTGUN}) AND (TITLE_ABS:{INFANT})',
    "antibiotics_early":   f'(TITLE_ABS:(antibiotic OR antibiotics OR probiotic OR probiotics OR synbiotic)) AND (TITLE_ABS:{INFANT}) AND (TITLE_ABS:{SHOTGUN}) AND (TITLE_ABS:{GUT})',
    "resistome":           f'(TITLE_ABS:(resistome OR "antibiotic resistance genes" OR "antimicrobial resistance genes")) AND (TITLE_ABS:{INFANT}) AND (TITLE_ABS:{GUT})',
    "virome_phage":        f'(TITLE_ABS:(virome OR phage OR bacteriophage)) AND (TITLE_ABS:{INFANT}) AND (TITLE_ABS:{GUT}) AND (TITLE_ABS:{SHOTGUN})',
    "twins_siblings":      f'(TITLE_ABS:(twin OR twins OR sibling OR siblings)) AND (TITLE_ABS:{INFANT}) AND (TITLE_ABS:{SHOTGUN})',
    "growth_outcomes":     f'(TITLE_ABS:(stunting OR malnutrition OR "growth faltering" OR kwashiorkor OR "severe acute malnutrition")) AND (TITLE_ABS:{INFANT}) AND (TITLE_ABS:{SHOTGUN})',
    # Broad recall net: no shotgun restriction. Used ONLY to measure how much the
    # shotgun-restricted grammar misses -- papers that do shotgun but never say so
    # in the abstract.
    "recall_net_nofilter": f'(TITLE_ABS:{INFANT}) AND (TITLE_ABS:{GUT}) AND (TITLE_ABS:(microbiome OR microbiota OR metagenomics OR metagenomic OR metagenome))',
}

KEEP = ["id", "source", "pmid", "pmcid", "doi", "title", "authorString",
        "journalTitle", "pubYear", "firstPublicationDate", "citedByCount",
        "isOpenAccess", "inEPMC", "inPMC", "hasSuppl", "hasTextMinedTerms",
        "hasReferences", "hasDbCrossReferences", "dbCrossReferenceList",
        "abstractText", "pubTypeList"]


def flatten(rec):
    out = {}
    for k in KEEP:
        v = rec.get(k)
        if isinstance(v, (dict, list)):
            v = json.dumps(v)[:4000]
        out[k] = v
    return out


def main():
    Path("lit").mkdir(exist_ok=True)
    seen, rows, yields = set(), [], []
    for name, q in FACETS.items():
        cache_f = Path("lit") / f"{name}.parquet"
        if cache_f.exists():
            df = pd.read_parquet(cache_f)
        else:
            t0 = time.time()
            n = HL.epmc_count(q, purpose=f"epmc_count:{name}")
            recs = HL.epmc_search_all(q, page_size=1000, cap=40000, purpose=f"epmc:{name}")
            df = pd.DataFrame([flatten(r) for r in recs])
            if len(df):
                df["facet"] = name
            df.to_parquet(cache_f, index=False)
            print(f"[{name}] count={n} fetched={len(df)} in {time.time()-t0:.0f}s", flush=True)
        if len(df) == 0 or "id" not in df.columns:
            yields.append({"facet": name, "n_hits": 0, "n_novel": 0, "query": q})
            print(f"[{name}] EMPTY -- query returned nothing", flush=True)
            continue
        ids = set(df["id"].dropna())
        novel = len(ids - seen)
        yields.append({"facet": name, "n_hits": len(df), "n_novel": novel, "query": q})
        seen |= ids
        rows.append(df)
        print(f"[{name}] hits={len(df):,} novel={novel:,} cum={len(seen):,}", flush=True)

    papers = pd.concat(rows, ignore_index=True)
    prov = (papers.groupby("id")["facet"].apply(lambda s: ";".join(sorted(set(s))))
            .rename("facets"))
    papers = papers.drop_duplicates(subset=["id"]).set_index("id")
    papers["facets"] = prov
    papers = papers.reset_index().drop(columns=["facet"])
    papers.to_parquet("papers_raw.parquet", index=False)
    pd.DataFrame(yields).to_csv("query_yield.csv", index=False)
    print(f"\nUNIQUE papers: {len(papers):,}")
    print("by source:", papers.groupby("source").size().to_dict())
    print("in PMC full text:", int((papers.inEPMC == "Y").sum()),
          "| open access:", int((papers.isOpenAccess == "Y").sum()),
          "| has suppl:", int((papers.hasSuppl == "Y").sum()))


if __name__ == "__main__":
    main()

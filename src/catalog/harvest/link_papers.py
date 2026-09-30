"""Deterministic paper<->study linking from accession mentions."""
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
import pandas as pd

OWN_SECTIONS = {"data_availability", "methods", "back_matter", "supplement_caption", "abstract"}
CITED_SECTIONS = {"results", "introduction", "discussion", "body_other"}
EXTERNAL_TYPES = {"geo", "ega", "dbgap", "gsa", "mgnify"}
REUSE_RX = r"(?i)\b(?:downloaded|obtained|retrieved|collected|acquired|were taken|publicly available|previously published|published (?:data|dataset|study|cohort)s?|re-?analy[sz]|reused|meta-?analysis|from (?:the )?(?:study|studies|cohort|dataset|project) (?:of|by)|existing (?:data|dataset)s?)\b"
OWN_RX = r"(?i)\b(?:deposited|submitted|have been uploaded|uploaded|are available (?:in|at|under|from) the|generated in this study|this study (?:are|is|have been) (?:available|deposited)|accession (?:number|no|code)s? [A-Z]{3}|under (?:the )?(?:BioProject|accession|project) (?:ID|number|no|accession)?)\b"

def aggregate(mentions, acc2study):
    """mentions: DataFrame of raw mentions. Returns (agg per paper x study, external per paper x accession)."""
    m = mentions.copy()
    m["study_accession"] = m["accession"].map(acc2study)
    ext = m[m.accession_type.isin(EXTERNAL_TYPES)].copy()
    mu = m.dropna(subset=["study_accession"]).copy()
    mu["sec_class"] = mu.source_section.apply(lambda s: "supplement" if str(s).startswith("supplement:") else s)
    import re
    mu["reuse_cue"] = mu.context.str.contains(REUSE_RX, regex=True)
    mu["own_cue"] = mu.context.str.contains(OWN_RX, regex=True)
    def _agg(g):
        secs = sorted(set(g.sec_class))
        gs = g.sort_values("sec_class", key=lambda s: s.map(lambda x: 0 if x == "data_availability" else 1 if x == "methods" else 2))
        ctx, ctx_secs = [], []
        for c, sc in zip(gs.context, gs.source_section):
            w = set(c.split())
            if all(len(w & set(k.split())) / max(1, len(w | set(k.split()))) < 0.6 for k in ctx):
                ctx.append(c); ctx_secs.append(sc)
            if len(ctx) >= 3:
                break
        return pd.Series({
            "n_mentions": len(g), "sections": secs, "accessions": sorted(set(g.accession))[:10],
            "n_accessions": g.accession.nunique(), "in_da": "data_availability" in secs,
            "in_own_sec": bool(set(secs) & OWN_SECTIONS), "only_cited_sec": not (set(secs) & OWN_SECTIONS) and not any(s == "supplement" for s in secs),
            "from_supplement": bool(g.from_supplement.any()), "reuse_cue": bool(g.reuse_cue.any()), "own_cue": bool(g.own_cue.any()),
            "contexts": ctx, "ctx_sections": ctx_secs})
    agg = mu.groupby(["paper_id", "pmcid", "study_accession"], dropna=False).apply(_agg, include_groups=False).reset_index()
    n_stud = agg.groupby("paper_id").study_accession.nunique().rename("n_universe_studies")
    agg = agg.merge(n_stud, on="paper_id")
    return agg, ext

def classify(agg):
    """Add deterministic decision columns."""
    det_da = agg.in_da & (agg.n_universe_studies == 1) & ~agg.reuse_cue
    det_single = (agg.n_universe_studies == 1) & agg.in_own_sec & ~agg.in_da & ~agg.reuse_cue
    det_supp_only = (agg.n_universe_studies == 1) & ~agg.in_own_sec & agg.from_supplement & ~agg.reuse_cue
    agg = agg.copy()
    agg["method"] = None; agg["relation"] = None; agg["confidence"] = None; agg["contested"] = True
    agg.loc[det_da, ["method", "relation", "confidence", "contested"]] = ["det_data_availability", "own_data", 0.9, False]
    agg.loc[det_single, ["method", "relation", "confidence", "contested"]] = ["det_single_mention", "own_data", 0.75, False]
    agg.loc[det_supp_only, ["method", "relation", "confidence", "contested"]] = ["det_single_mention", "own_data", 0.6, False]
    agg["contest_reason"] = None
    agg.loc[agg.contested & (agg.n_universe_studies >= 2), "contest_reason"] = "multi_study"
    agg.loc[agg.contested & (agg.n_universe_studies == 1) & agg.reuse_cue, "contest_reason"] = "reuse_cue_in_context"
    agg.loc[agg.contested & (agg.n_universe_studies == 1) & ~agg.reuse_cue, "contest_reason"] = "cited_section_only"
    return agg

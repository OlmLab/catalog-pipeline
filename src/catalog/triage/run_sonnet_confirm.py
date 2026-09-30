"""Sonnet rubric confirmation of candidate studies. Set SLICE (parquet path), OUT_PREFIX,
optionally MODEL (default claude-sonnet-5) and REPLICATE (int tag) before exec.
Expects llm_batch_common imported, validators loaded, `host` in namespace."""
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
import json, pandas as pd
from llm_batch_common import run_batches, V

MODEL = globals().get("MODEL") or resolve_model("rubric")
REPLICATE = globals().get("REPLICATE", 1)
BATCH = globals().get("BATCH", 4)
MAX_TOKENS = globals().get("MAX_TOKENS", 6000)
REASON_CODES = sorted(V["REASON_CODES"]) if isinstance(V.get("REASON_CODES"), (set, list, tuple, dict)) else [
    "assay_amplicon", "assay_amplicon_misfiled", "assay_rna", "assay_isolate_genome", "assay_other_nonshotgun",
    "assay_assembly_only", "host_nonhuman", "host_environmental", "host_synthetic", "age_adult_only",
    "age_child_over_36m", "age_maternal_only", "age_unknown_no_evidence", "site_excluded", "site_unknown",
    "fp_salmonella_infantis", "fp_bifido_infantis", "fp_name_only", "access_controlled", "access_suppressed",
    "dup_mirror", "dup_reanalysis"]
SOURCES = ["study.title", "study.description", "sample.title", "sample.attr.host_scientific_name",
           "sample.attr.host_body_site", "sample.attr.age", "sample.attr.dev_stage", "sample.attr.isolation_source",
           "sample.attr.environmental_medium", "run.library_strategy", "run.library_source", "run.instrument_model",
           "sample_id_pattern", "study.alias", "paper.title", "paper.abstract", "paper.fulltext.data_availability", "paper.supp.table"]

RUBRIC = """You are screening sequencing-archive study records for a systematic catalog of
INFANT GUT SHOTGUN METAGENOMICS. Decide whether each study belongs in the catalog.

INCLUDE only if ALL FOUR hold:
 1. HUMAN subjects. Not mouse, pig/piglet, macaque, calf, chick, or any animal model.
 2. DNA SHOTGUN metagenomics. Whole-metagenome shotgun sequencing of a microbial
    community. NOT 16S/18S/ITS amplicon. NOT RNA-seq or metatranscriptomics. NOT a
    cultured single-isolate genome. NOT proteomics or metabolomics.
 3. GUT or a retained linked site. Gut/stool/faeces/meconium/intestinal is primary.
    Breast milk, maternal faeces, and vaginal samples count ONLY if the study also
    samples infants; they are retained as cohort context, never on their own.
 4. At least some subjects aged 0 to 36 MONTHS (birth through third birthday),
    including preterm neonates. A study of 4-year-olds or adults does not qualify.

CRITICAL TRAPS, all observed in this archive:
 * "Infantis" is a name collision. Salmonella enterica serovar Infantis and
   Bifidobacterium longum subsp. infantis are BACTERIA. Check serovar/sub_species/strain.
 * The deposited organism taxon is NOT the body site. A study filed under taxon
   "human gut metagenome" may actually be adenoid, oral, skin, sputum or nasal.
   Trust study title, description, sample titles, body-site, environmental-medium
   and isolation-source fields over the taxon.
 * Animal studies use infant-like words (piglet, pup, neonatal mouse, suckling).
 * Simulated, mock, and benchmark communities look like real cohorts.
 * Adult cohorts sometimes contain a small infant subgroup -- that still INCLUDES,
   but say so and estimate how many samples.
 * Maternal-only or pregnancy-only cohorts with no infant sampling are EXCLUDED.
 * "kid", "rat", "cat" inside longer words are not hosts.

EVIDENCE RULES:
 * Each verdict carries 1-3 evidence items {source, quote}; quote is copied VERBATIM
   from the record field named by source. HARD LIMIT: at most 12 words per quote — pick the
   shortest decisive span (3-8 words ideal); longer quotes are rejected by the validator.
   Never paraphrase or invent. Return a verdict for EVERY study accession given.
 * age_evidence_source: "sample_attribute", "study_text", or "none". If "none", the
   verdict must be "uncertain" unless the study text is unambiguous.
 * An exclude verdict MUST carry exactly one reason_code from the controlled list.
 * Use "uncertain" honestly; uncertain records are escalated at no cost.
 * You are shown prior signals (a deterministic keyword flag, a cheap-model screen, and
   sometimes a prior verdict). They are hints, not evidence; judge from the record."""

TOOL = {
    "name": "record_verdicts",
    "description": "Record the triage verdict for each study in the batch, same order as given.",
    "input_schema": {"type": "object", "properties": {"studies": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "study_accession": {"type": "string"},
            "verdict": {"type": "string", "enum": ["include", "exclude", "uncertain"]},
            "is_human": {"type": "string", "enum": ["yes", "no", "unsure"]},
            "is_dna_shotgun": {"type": "string", "enum": ["yes", "no", "unsure"]},
            "is_gut_or_linked": {"type": "string", "enum": ["yes", "no", "unsure"]},
            "has_infant_0_36m": {"type": "string", "enum": ["yes", "no", "unsure"]},
            "age_evidence_source": {"type": "string", "enum": ["sample_attribute", "study_text", "none"]},
            "body_site_call": {"type": "string"},
            "n_infant_samples_est": {"type": "integer"},
            "reason_code": {"type": "string", "enum": REASON_CODES + ["none"]},
            "evidence": {"type": "array", "minItems": 1, "maxItems": 3, "items": {"type": "object", "properties": {
                "source": {"type": "string", "enum": SOURCES}, "quote": {"type": "string"}}, "required": ["source", "quote"]}},
            "confidence": {"type": "number"},
            "reasoning": {"type": "string", "description": "<=2 sentences"}},
        "required": ["study_accession", "verdict", "is_human", "is_dna_shotgun", "is_gut_or_linked", "has_infant_0_36m",
                     "age_evidence_source", "reason_code", "evidence", "confidence", "reasoning"]}}},
        "required": ["studies"]}}


def fmt(s):
    rec = json.loads(s.record_json) if isinstance(s.record_json, str) else {}
    lines = [f"### STUDY {s.study_accession}",
             f"study.title: {s.study_title}",
             f"study.description: {(s.study_description or '')[:1500] or '(none)'}",
             f"run.library_strategy: {s.library_strategies} | run.library_source: {s.library_sources} | run.instrument_model: {s.instrument_models}",
             f"n_samples={s.n_samples} n_runs={s.n_runs} first_public={s.first_public_min}",
             f"sample.attr.host_scientific_name: {s.host_scientific_names}",
             f"sample.attr.host_body_site: {s.host_body_sites} | sample.attr.isolation_source: {s.isolation_sources}",
             f"sample.attr.age: {s.ages} | sample.attr.dev_stage: {s.dev_stages}",
             f"sample.attr.environmental_medium: {rec.get('env_medium')}",
             f"sample.title (sample): {rec.get('sample_titles') or s.sample_titles_sample}",
             f"PRIOR SIGNALS (hints only): keyword_flag={bool(s.sig_infant_hit)} title_pattern_flag={bool(s.sig_infant_title)} patterns={s.matched_patterns} cheap_screen={s.screen_value} prior_verdict={s.prior_verdict}"]
    # optional linked-paper context (wave 2: studies reached through the literature channel)
    pt = getattr(s, "paper_title", None)
    if isinstance(pt, str) and pt:
        lines += [f"LINKED PAPER (relation={getattr(s, 'paper_relation', 'unknown')}, link_method={getattr(s, 'paper_link_method', 'unknown')}):",
                  f"paper.title: {pt}",
                  f"paper.abstract: {str(getattr(s, 'paper_abstract', '') or '')[:1800]}",
                  f"paper.fulltext.data_availability: {str(getattr(s, 'paper_link_context', '') or '')[:600]}",
                  f"paper.supp.table: {str(getattr(s, 'supp_evidence', '') or '')[:900]}",
                  "NOTE: paper.supp.table lines summarise a per-sample supplementary table linked to this accession (file[sheet!column]: rows with age <= 3 y / total, example values, whether sample IDs map to this study's accessions). Cite it as source 'paper.supp.table'. Quote must be <=12 words (e.g. 'age column: 13 of 191 rows <= 3 y').",
                  "NOTE: an adult cohort whose paper documents an infant subgroup that was sequenced and deposited under this accession INCLUDES; cite paper.abstract or paper.fulltext.data_availability and estimate n_infant_samples_est."]
    return "\n".join(str(x) for x in lines) + "\n"


df = pd.read_parquet(SLICE)
requests, metas = [], []
for i in range(0, len(df), BATCH):
    b = df.iloc[i:i + BATCH]
    prompt = f"Judge the following {len(b)} archive study records. Return one verdict per study in the same order.\n\n" + "\n".join(fmt(s) for s in b.itertuples())
    requests.append({"prompt": prompt, "system": RUBRIC, "model": MODEL, "tools": [TOOL],
                     "tool_choice": {"type": "tool", "name": TOOL["name"]}, "max_tokens": MAX_TOKENS})
    metas.append({"ids": list(b.study_accession), "slots": ["triage_verdict"]})


def make_rows(meta, parsed, res):
    out = []
    got = {str(p.get("study_accession")): p for p in (parsed.get("studies") or []) if isinstance(p, dict)}
    for rid in meta["ids"]:
        p = got.get(rid)
        if not p:
            out.append(V["sentinel_row"](rid, "triage_verdict", MODEL, note="study missing from batch output"))
            continue
        verdict = p.get("verdict")
        outcome = {"include": "included", "exclude": "excluded_llm", "uncertain": "unsure_adjudicated"}.get(verdict, "validator_rejected")
        rc = p.get("reason_code")
        rc = None if rc in (None, "none", "") else rc
        ev = [{"source": e.get("source"), "quote": str(e.get("quote", ""))[:120]} for e in (p.get("evidence") or []) if isinstance(e, dict)]
        out.append({"record_id": rid, "slot": "triage_verdict", "value": verdict, "outcome": outcome,
                    "confidence": p.get("confidence"), "reason_code": rc, "evidence": ev, "model": MODEL,
                    "replicate": REPLICATE,
                    "is_human": p.get("is_human"), "is_dna_shotgun": p.get("is_dna_shotgun"),
                    "is_gut_or_linked": p.get("is_gut_or_linked"), "has_infant_0_36m": p.get("has_infant_0_36m"),
                    "age_evidence_source": p.get("age_evidence_source"), "body_site_call": p.get("body_site_call"),
                    "n_infant_samples_est": p.get("n_infant_samples_est"), "reasoning": str(p.get("reasoning", ""))[:400]})
    return out


confirm_df, stats = run_batches(requests, metas, make_rows, f"{OUT_PREFIX}.parquet", MODEL,
                                max_concurrency=6, checkpoint_every=200, log_path=f"{OUT_PREFIX}_stats.json")
print(json.dumps(stats))
print(confirm_df["value"].value_counts(dropna=False).to_dict(), confirm_df["outcome"].value_counts().to_dict())

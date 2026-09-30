"""
Step 3 -- massively parallel per-study infant triage.

Architecture note. The plan calls for every enumerated study to be judged rather
than only the uncertain ones. Delegated sub-agents are the wrong instrument for
that: each study judgement is a single stateless read over a record already in
the local cache, with no tool use required. So the fan-out runs through parallel
model calls (host.llm list form, which dispatches concurrently) and delegated
agents are reserved for cases that genuinely need retrieval and reasoning --
contested dataset-to-paper links and cohort cluster adjudication, later steps.

Two tiers:
  Tier 1  every study, reasoning model, strict rubric, structured output.
  Tier 2  re-judge with the strongest model wherever Tier 1 said include or
          uncertain, or where a deterministic signal contradicts the verdict.
Disagreements between tiers form the adjudication queue.
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
import scope_constants as SC

RUBRIC = """You are screening sequencing-archive study records for a systematic catalog of
INFANT GUT SHOTGUN METAGENOMICS. Decide whether this study belongs in the catalog.

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
   Bifidobacterium longum subsp. infantis are BACTERIA. A study sequencing those
   organisms is not an infant study. Check serovar/sub_species/strain fields.
 * The deposited organism taxon is NOT the body site. A study filed under taxon
   "human gut metagenome" may actually be adenoid, oral, skin, sputum or nasal --
   this is real and common. Trust the study title, sample titles, body-site,
   environmental-medium and isolation-source fields over the taxon.
 * Animal studies often use infant-like words (piglet, pup, neonatal mouse,
   suckling). Check host_scientific_names. Rat, mouse and goat gut-metagenome
   studies are present in this frame because the taxon is not human-specific.
 * Simulated, mock, and benchmark communities look like real cohorts.
 * Adult cohorts sometimes contain a small infant subgroup -- that still INCLUDES,
   but say so and estimate how many samples.
 * Maternal-only or pregnancy-only cohorts with no infant sampling are EXCLUDED.

EVIDENCE RULES:
 * evidence_quote must be copied VERBATIM from the record, never paraphrased or
   invented. If nothing in the record supports your verdict, quote the most
   relevant field and say so in the reasoning.
 * age_evidence_source records WHERE the age evidence came from:
   "sample_attribute" (age/dev_stage/host fields), "study_text" (title, sample
   titles, project name), or "none" (no age evidence at all -- then the verdict
   must be "uncertain", not "include", unless the study text is unambiguous).
 * Use "uncertain" honestly. A record too thin to judge is uncertain, not exclude.
   Uncertain records are escalated, so there is no cost to admitting doubt.
"""

TOOL = {
    "name": "record_verdict",
    "description": "Record the triage verdict for one archive study.",
    "input_schema": {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": ["include", "exclude", "uncertain"]},
            "is_human": {"type": "boolean"},
            "is_dna_shotgun": {"type": "boolean"},
            "is_gut_or_linked": {"type": "boolean"},
            "has_infant_0_36m": {"type": "boolean"},
            "age_evidence_source": {"type": "string",
                                    "enum": ["sample_attribute", "study_text", "none"]},
            "evidence_quote": {"type": "string",
                               "description": "VERBATIM text copied from the record."},
            "reason_code": {"type": "string", "enum": sorted(SC.REASON_CODES) + [""],
                            "description": "Required when verdict is exclude; must be one of "
                                           "the controlled codes. Empty string otherwise."},
            "n_infant_samples_est": {"type": "integer",
                                     "description": "Best estimate of in-scope infant samples; 0 if none."},
            "body_site_call": {"type": "string",
                               "enum": ["gut", "milk", "maternal_fecal", "vaginal",
                                        "other_linked", "excluded_site", "unknown"]},
            "confidence": {"type": "number", "description": "0.0 to 1.0"},
            "reasoning": {"type": "string", "description": "2-3 sentences maximum."},
        },
        "required": ["verdict", "is_human", "is_dna_shotgun", "is_gut_or_linked",
                     "has_infant_0_36m", "age_evidence_source", "evidence_quote",
                     "reason_code", "n_infant_samples_est", "body_site_call",
                     "confidence", "reasoning"],
    },
}

RECORD_FIELDS = [
    ("study_accession", "Accession"), ("study_title", "Study title"),
    ("project_name", "Project name"), ("center_name", "Center"),
    ("n_runs", "Runs"), ("n_samples", "Samples"),
    ("first_public_min", "First public"),
    ("library_strategies", "Library strategies"),
    ("library_sources", "Library sources"),
    ("library_selections", "Library selection"),
    ("instrument_models", "Instruments"),
    ("base_count_median", "Median bases/run"),
    ("scientific_names", "Deposited organism taxa"),
    ("host_scientific_names", "Host organism"),
    ("host_body_sites", "Host body site field"),
    ("host_status", "Host status"), ("host_phenotype", "Host phenotype"),
    ("ages", "Age field values"), ("dev_stages", "Dev stage field values"),
    ("diseases", "Disease field"), ("countries", "Countries"),
    ("isolation_sources", "Isolation source"),
    ("environmental_medium", "Environmental medium"),
    ("serovars", "Serovar field"), ("sub_species", "Sub-species field"),
    ("strains", "Strain field"), ("isolates", "Isolate field"),
    ("sample_titles_sample", "Sample titles (up to 25)"),
    ("checklists", "ENA checklist"),
]


def render_record(row):
    parts = []
    for key, label in RECORD_FIELDS:
        v = row.get(key)
        if v is None or (isinstance(v, float) and pd.isna(v)):
            continue
        s = str(v).strip()
        if not s or s in ("nan", "[]"):
            continue
        if len(s) > 1200:
            s = s[:1200] + " ...[truncated]"
        parts.append(f"{label}: {s}")
    return "\n".join(parts)


def build_requests(studies, model, max_tokens=1200):
    reqs, keys = [], []
    for _, row in studies.iterrows():
        reqs.append({
            "prompt": "ARCHIVE STUDY RECORD\n--------------------\n" + render_record(row)
                      + "\n--------------------\nJudge this study with record_verdict.",
            "system": RUBRIC,
            "tools": [TOOL],
            "tool_choice": {"type": "tool", "name": "record_verdict"},
            "model": model,
            "max_tokens": max_tokens,
        })
        keys.append(row["study_accession"])
    return reqs, keys


def parse_results(results, keys, model, tier):
    out = []
    for key, r in zip(keys, results):
        rec = {"study_accession": key, "tier": tier, "model_used": model}
        if not isinstance(r, dict) or r.get("error"):
            rec.update({"verdict": "ERROR",
                        "error": str(r.get("error") if isinstance(r, dict) else r)[:300]})
            out.append(rec); continue
        tu = r.get("tool_use")
        payload = tu[0].get("input") if isinstance(tu, list) and tu else (
            tu.get("input") if isinstance(tu, dict) else None)
        if not payload:
            rec.update({"verdict": "ERROR", "error": "no tool_use in response"})
            out.append(rec); continue
        rec.update(payload)
        out.append(rec)
    return pd.DataFrame(out)

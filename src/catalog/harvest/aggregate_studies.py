"""
Step 2b -- collapse run-level records to study-level triage records.

Produces one row per ENA study with everything a triage judge needs without
another network call: assay composition, technical covariates, the distinct
values of every host/body-site/age field its samples carry, and deterministic
flags for the known false-positive classes.

Deterministic signals here are used for PRIORITISATION and for auditing the
judge -- never to exclude a study before it is judged. The adenoid study filed
under "human gut metagenome" (ERR17534130 / PRJEB72800, found in the Step 1
smoke test) is the standing reminder that archive fields cannot decide inclusion.
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

import numpy as np
import pandas as pd

# (sys.path handled by the repo layout shim above)
import scope_constants as SC

MAXV = 25


def _distinct(s, maxv=MAXV):
    v = [x for x in pd.unique(s.dropna().astype(str)) if x.strip() and x.strip() != "nan"]
    return v[:maxv]


def _joined(s, maxv=MAXV):
    return " | ".join(_distinct(s, maxv))


def _col(g, name):
    return g[name] if name in g else pd.Series(dtype=str)


_RX_CACHE = {}


def _flag_any(text, patterns):
    """
    Word-boundary matching. Plain substring search produced 1,576 spurious
    non-human-host hits on the first pass -- 'rat' inside "ulcerative", 'cat'
    inside "applications", 'kid' inside "kidney", 'bat' inside "incubation".
    """
    t = (text or "").lower()
    key = id(patterns)
    if key not in _RX_CACHE:
        _RX_CACHE[key] = [(p, re.compile(r"(?<![a-z])" + re.escape(p.lower()) + r"(?![a-z])"))
                          for p in patterns]
    return sorted({p for p, rx in _RX_CACHE[key] if rx.search(t)})


def amplicon_tells(g):
    """Direct evidence a 'shotgun' study is actually amplicon."""
    tells = []
    for field in ("target_gene", "library_name"):
        for v in _distinct(_col(g, field), 40):
            if any(k in v.lower() for k in SC.AMPLICON_TELL_VALUES):
                tells.append(f"{field}={v}")
    if any("pcr" in v.lower() for v in _distinct(_col(g, "library_selection"))):
        tells.append("library_selection=PCR")
    return tells


INFANT_RX = re.compile(
    r"\b(infant|infants|infancy|neonat\w*|newborn\w*|preterm|pre-term|premature|"
    r"prematurity|baby|babies|toddler\w*|weaning|weaned|breast-?f\w+|breastmilk|"
    r"breast milk|formula-?f\w+|colostrum|meconium|nicu|birth cohort|first year of life|"
    r"first 1000 days|first thousand days|early life|early-life|postnatal|"
    r"month-old|months of age|day of life|mother-infant|maternal-infant|"
    r"delivery mode|caesarean|cesarean|c-section|vaginal delivery|necrotizing enterocolitis|"
    r"necrotising enterocolitis|\bnec\b|late-onset sepsis)\b", re.I)

ADULT_RX = re.compile(r"\b(adult|adults|elderly|geriatric|aged \d\d|postmenopaus\w+|"
                      r"university students)\b", re.I)


def build(runs_path="universe_runs_lean.parquet", out="universe_studies.parquet"):
    runs = pd.read_parquet(runs_path)
    for c in ["read_count", "base_count", "nominal_length"]:
        if c in runs:
            runs[c] = pd.to_numeric(runs[c], errors="coerce")

    rows = []
    for study, g in runs.groupby("study_accession", sort=False):
        title = _joined(g["study_title"], 3)
        stitles = _distinct(g["sample_title"], 40)
        blob = " ".join([title, " ".join(stitles), _joined(_col(g, "project_name"), 5),
                         _joined(_col(g, "isolation_source")), _joined(_col(g, "host_body_site")),
                         _joined(_col(g, "disease")), _joined(_col(g, "experimental_factor")),
                         _joined(_col(g, "environmental_medium"), 10)])
        bc = g["base_count"]
        rows.append({
            "study_accession": study,
            "secondary_study_accession": _joined(g["secondary_study_accession"], 3),
            "study_title": title,
            "project_name": _joined(_col(g, "project_name"), 3),
            "center_name": _joined(g["center_name"], 5),
            "n_runs": len(g),
            "n_samples": g["sample_accession"].nunique(),
            "first_public_min": g["first_public"].min(),
            "first_public_max": g["first_public"].max(),
            "library_strategies": json.dumps(g["library_strategy"].value_counts().to_dict()),
            "library_sources": _joined(g["library_source"], 5),
            "library_selections": _joined(g["library_selection"], 8),
            "library_layouts": _joined(g["library_layout"], 4),
            "instrument_platforms": _joined(g["instrument_platform"], 6),
            "instrument_models": _joined(g["instrument_model"], 8),
            "base_count_median": float(np.nanmedian(bc)) if bc.notna().any() else None,
            "base_count_min": float(np.nanmin(bc)) if bc.notna().any() else None,
            "read_count_median": float(np.nanmedian(g["read_count"])) if g["read_count"].notna().any() else None,
            "tax_ids": _joined(g["tax_id"], 10),
            "scientific_names": _joined(g["scientific_name"], 10),
            "host_tax_ids": _joined(g["host_tax_id"], 6),
            "host_scientific_names": _joined(g["host_scientific_name"], 6),
            "host_body_sites": _joined(g["host_body_site"], 15),
            "host_status": _joined(_col(g, "host_status"), 10),
            "host_phenotype": _joined(_col(g, "host_phenotype"), 15),
            "ages": _joined(g["age"], 30),
            "dev_stages": _joined(g["dev_stage"], 15),
            "diseases": _joined(g["disease"], 15),
            "countries": _joined(g["country"], 12),
            "isolation_sources": _joined(_col(g, "isolation_source"), 15),
            "environmental_medium": _joined(_col(g, "environmental_medium"), 10),
            "extraction_protocols": _joined(_col(g, "extraction_protocol"), 8),
            "checklists": _joined(g["checklist"], 5),
            "sample_titles_sample": " | ".join(stitles[:25]),
            "serovars": _joined(_col(g, "serovar"), 8),
            "sub_species": _joined(_col(g, "sub_species"), 8),
            "strains": _joined(_col(g, "strain"), 10),
            "isolates": _joined(_col(g, "isolate"), 10),
            "found_by": _joined(g["found_by"], 12),
            "sig_infant_terms": json.dumps(sorted({m.lower() for m in INFANT_RX.findall(blob)})),
            "sig_infant_hit": bool(INFANT_RX.search(blob)),
            "sig_adult_hit": bool(ADULT_RX.search(blob)),
            "sig_nonhuman_host": json.dumps(_flag_any(
                blob + " " + _joined(g["host_scientific_name"], 6), SC.HOST_EXCLUDE_PATTERNS)),
            "sig_false_positive": json.dumps(_flag_any(blob, SC.FALSE_POSITIVE_PATTERNS)),
            "sig_synthetic": json.dumps(_flag_any(blob, SC.SYNTHETIC_DATA_PATTERNS)),
            "sig_amplicon_tells": json.dumps(amplicon_tells(g)),
            "sig_body_site_primary": bool(any(b in blob.lower() for b in SC.BODY_SITE_PRIMARY)),
            "sig_body_site_excluded": json.dumps(_flag_any(blob, SC.BODY_SITE_EXCLUDE)),
            "sig_has_age_field": bool(g["age"].notna().any() or g["dev_stage"].notna().any()),
        })

    st = pd.DataFrame(rows)
    st.to_parquet(out, index=False)
    return st


if __name__ == "__main__":
    st = build()
    print(f"studies: {len(st):,}")
    print(f"  infant term hit       : {st.sig_infant_hit.sum():,}")
    print(f"  age/dev_stage present : {st.sig_has_age_field.sum():,}")
    print(f"  amplicon tells        : {(st.sig_amplicon_tells != '[]').sum():,}")
    print(f"  non-human host hit    : {(st.sig_nonhuman_host != '[]').sum():,}")
    print(f"  false-positive hit    : {(st.sig_false_positive != '[]').sum():,}")
    print(f"  synthetic hit         : {(st.sig_synthetic != '[]').sum():,}")

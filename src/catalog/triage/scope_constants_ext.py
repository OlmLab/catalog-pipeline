"""scope_constants_ext.py — scope_constants v3 + the four extension fields (track 'Field extension', 2026-09-25).

Import as a drop-in for scope_constants: `from scope_constants_ext import *` exposes everything in
scope_constants plus EXTENSION_FIELDS / EXTENSION_VOCAB / EXTENSION_ATTR_KEYS documented below.
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
from scope_constants import *          # noqa: F401,F403  (v3 constants unchanged)
import scope_constants as _base

EXTENSION_VERSION = "2026-09-25.ext1"

# ------------------------------------------------------------------ extension fields
# health_condition: the INFANT's clinical status / study group at sampling. Never a maternal condition,
#   never the study's disease focus (a NEC study has NEC-free controls), never a cohort-wide statement
#   from paper text (that is group scope, route R3, out of this track). Single-valued: when a value
#   encodes two things (e.g. 'undernourished_probiotic') the clinical status wins and the trial arm is
#   recorded in parse_note.
# multiple_birth: singleton / twin / triplet_or_more from explicit twin/multiple-gestation attributes or
#   twin-pair codes. 'not applicable' on a twin-id column = singleton.
# sibling_in_study: another ENROLLED infant from the same family is in the same study deposit. 'yes' from
#   explicit columns (twin_in_study, 'Twin sibling to subject X', pair codes with both members present) or
#   from a family/household/dyad identifier shared by >=2 distinct infant subjects; 'no' only when the study
#   carries a family identifier for the infant and exactly one infant subject has that identifier.
#   Sibling COUNTS (num_siblings, older_siblings, sibling_in_family) are household composition, not
#   enrolment -> never used.
# geo_subregion: free text normalised to 'City, Region' (or the single sub-national token when only one
#   level is given) from 'Country: City', 'Country:State:City', 'Country: City, ST' patterns and from
#   region/state/locality/village attributes. Hospitals, labs and urban/rural class are not places.
#   Coordinates are NEVER reverse-geocoded into a city name.
EXTENSION_VOCAB = {
    "health_condition": {"healthy_control", "preterm_nicu", "nec", "sepsis_or_infection", "ibd_or_gi_disease",
                         "allergy_or_atopy", "malnutrition", "antibiotic_or_probiotic_trial", "other_disease", "unknown"},
    "multiple_birth": {"singleton", "twin", "triplet_or_more", "unknown"},
    "sibling_in_study": {"yes", "no", "unknown"},
    "geo_subregion": None,   # free text 'City, Region'
}
EXTENSION_FIELDS = list(EXTENSION_VOCAB)
TARGET_FIELDS_EXT = list(_base.TARGET_FIELDS) + EXTENSION_FIELDS

# 'unknown' is a vocabulary member for completeness of the controlled set but is NEVER committed as a
# determination row (Rule 3: omit rather than guess). It appears only in ext_norm_map.csv.
EXTENSION_NEVER_COMMIT = {"unknown"}

# Attribute keys mapped per field (route R1). Keys in EXTENSION_ATTR_SKIP were reviewed and rejected.
EXTENSION_ATTR_KEYS = {
    "health_condition": ["host_disease", "host_disease_stat", "host_phenotype", "disease", "diagnosis", "condition",
                         "conditions", "any_condition", "nourishment_status_group", "is_healthy", "ibd_diagnosis",
                         "history_of_congenital_heart_disease_0_no_1_yes", "history_of_congenital_heart_disease_0_no_1_yes_1"],
    "multiple_birth": ["has_twin", "twin_gestation", "twin_pair", "twin_or_singleton", "twin_id", "twin_in_study", "is_twin",
                       "twin_gestation_0_no_1_yes", "twin_gestation_0_no_1_yes_1", "type_of_twin", "twins",
                       "maternal_complication_twin", "host_family_relationship"],
    "sibling_in_study": ["twin_in_study", "twins", "twin_pair", "twin_mother_id", "host_family_relationship",
                         "family_id", "host_family_id", "family_number", "dyad_id", "host_family", "sample_pair_id"],
    "geo_subregion": ["geo_loc_name", "geographic_location", "geographic_location_region_and_locality", "state",
                      "location", "site_village"],
}
EXTENSION_ATTR_SKIP = {
    # American Gut Project (PRJEB11419) adult self-report questionnaire keys: not infant-named
    "skin_condition": "AGP adult questionnaire", "clinical_condition": "AGP adult questionnaire",
    "lung_disease": "AGP adult questionnaire", "cardiovascular_disease": "AGP adult questionnaire",
    "liver_disease": "AGP adult questionnaire", "kidney_disease": "AGP adult questionnaire",
    "ibd_diagnosis_refined": "AGP adult questionnaire", "subset_healthy": "AGP adult questionnaire",
    "ibd_diagnosis@PRJEB11419": "AGP adult questionnaire (key kept for PRJNA1045596)",
    "covid_*": "adult COVID questionnaire", "pm_*": "adult participation questionnaire",
    "study_disease": "study focus, not per-infant status (NEC study includes controls)",
    "host_disease_status": "PRJEB111647 values are delivery mode x trial arm; intervention unspecified",
    "health_state": "encodes delivery mode, not condition",
    "phenotype": "encodes sex and age, not condition",
    "current_disease": "uninterpretable code ('2') / not applicable",
    "gbs_status": "GBS colonisation status is not infection",
    "baby_status": "Normal/Borderline/Abnormal without a stated instrument",
    "weightstatus": "maternal (1 infant-role row)", "mother_health_status": "maternal",
    "fever_in_hospital": "symptom, not condition", "diarrhea_in_hospital": "symptom, not condition",
    "stool_parasite": "count/code", "parasite": "count/code",
    "duration_of_hospitalization*": "not a condition", "days_in_hospital": "not a condition",
    "sibling_in_family": "household composition, not enrolment", "num_siblings": "count", "older_siblings": "count",
    "siblings": "count", "sibling": "count", "totwins": "not a twin indicator (values 38..266)",
    "geographic_location_latitude": "coordinates never reverse-geocoded", "geographic_location_longitude": "coordinates never reverse-geocoded",
    "hospital": "institution, not a place", "physical_specimen_location": "storage institution", "physical_location": "institution",
    "geographic_location_country_and_or_sea_region": "country level only", "geographic_location_country_region_area": "country level only",
    "economic_region": "AGP", "census_region": "AGP",
}

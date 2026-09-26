"""
Machine-checkable scope constants for the Infant Shotgun Metagenome Catalog.

Every harvest, triage, and export step imports from here. Nothing downstream may
hardcode a scope decision -- if a filter isn't expressed in this file, it doesn't
exist. This is what stops scope drift across a 12-step, multi-session pipeline.

Scope locked 2026-09-14 (user decisions):
  * DNA shotgun metagenomics ONLY. No amplicon, no RNA, no proteomics/metabolomics.
  * Human subjects 0-36 months.
  * Gut/stool primary; maternal-fecal / breast-milk / vaginal retained ONLY when
    they belong to an enumerated infant cohort, tagged by body_site.
  * Cultured isolate genomes recorded in a side table, out of primary scope.
"""

SCOPE_VERSION = "2026-09-14.1"

# ---------------------------------------------------------------- assay scope

# ENA/SRA library_strategy values we ACCEPT as DNA shotgun metagenomics.
# "OTHER" is accepted only into an adjudication queue, never silently included:
# a nontrivial number of legitimate shotgun deposits are filed as OTHER.
LIBRARY_STRATEGY_INCLUDE = {"WGS", "WXS"}
LIBRARY_STRATEGY_ADJUDICATE = {"OTHER", "Targeted-Capture", "ssRNA-seq"}

# Hard excludes. AMPLICON is the whole 16S/18S/ITS world the user ruled out.
LIBRARY_STRATEGY_EXCLUDE = {
    "AMPLICON", "RNA-Seq", "miRNA-Seq", "ncRNA-Seq", "FL-cDNA", "EST",
    "ChIP-Seq", "ATAC-seq", "Bisulfite-Seq", "MRE-Seq", "MeDIP-Seq",
    "MBD-Seq", "Tn-Seq", "VALIDATION", "FINISHING", "CLONE", "CLONEEND",
    "POOLCLONE", "RAD-Seq", "Hi-C", "SELEX", "CTS", "GBS", "Synthetic-Long-Read",
}

# library_source: METAGENOMIC is the target. GENOMIC = cultured isolate (side table).
LIBRARY_SOURCE_INCLUDE = {"METAGENOMIC"}
LIBRARY_SOURCE_SIDE_TABLE = {"GENOMIC"}          # isolate genomes, out of primary scope
LIBRARY_SOURCE_EXCLUDE = {
    "METATRANSCRIPTOMIC", "TRANSCRIPTOMIC", "TRANSCRIPTOMIC SINGLE CELL",
    "VIRAL RNA", "SYNTHETIC", "OTHER",
}

# Platforms that cannot produce usable shotgun metagenomes for our purposes.
INSTRUMENT_PLATFORM_EXCLUDE = {"CAPILLARY"}

# ---------------------------------------------------------------- taxon scope

# NCBI taxids used as the enumeration frame. Gut-relevant metagenome taxa plus
# the linked-body-site taxa we retain when they belong to an infant cohort.
TAXA_PRIMARY = {
    408170:  "human gut metagenome",
    749906:  "gut metagenome",
    1861841: "feces metagenome",
    646099:  "human metagenome",
    3007725: "human feces metagenome",
}
TAXA_LINKED_BODY_SITE = {
    1633408: "human milk metagenome",
    1131769: "milk metagenome",
    1348798: "human vaginal metagenome",
}
# Probed for cross-contamination of the frame, never included as primary.
TAXA_EXCLUDE_CHECK = {
    447426: "human oral metagenome",
    412755: "human skin metagenome",
    1131266: "human nasopharyngeal metagenome",
}

TAXA_ALL_FRAME = {**TAXA_PRIMARY, **TAXA_LINKED_BODY_SITE}

# ---------------------------------------------------------------- age scope

AGE_MAX_DAYS = 1096          # 36 months, inclusive (3 * 365.25, rounded up)
AGE_MIN_DAYS = 0             # birth; gestational-age-only samples handled separately
PRETERM_GA_WEEKS_MAX = 37.0  # < 37 completed weeks = preterm (WHO)

# Sample-attribute keys that carry age, in rough order of reliability.
AGE_ATTRIBUTE_KEYS = [
    "host_age", "age", "host age", "age_at_collection", "collection_age",
    "host_life_stage", "life_stage", "dev_stage", "host_dev_stage",
    "age_days", "age_months", "age_years", "infant_age", "day_of_life",
    "days_post_birth", "postnatal_age", "corrected_age", "host_subject_age",
]
GESTATIONAL_AGE_KEYS = [
    "gestational_age", "gestational_age_at_birth", "ga_weeks",
    "gestation", "birth_gestational_age", "host_gestational_age",
]

# Life-stage strings that qualify as in-scope without a numeric age.
LIFE_STAGE_INCLUDE = {
    "infant", "infants", "neonate", "neonatal", "newborn", "baby", "babies",
    "preterm", "premature", "preterm infant", "toddler", "child (0-3)",
    "breast-fed infant", "suckling", "postnatal",
}
LIFE_STAGE_EXCLUDE = {
    "adult", "adults", "elderly", "senior", "child", "children", "adolescent",
    "teenager", "juvenile", "mother", "maternal", "pregnant", "prenatal", "fetal",
}

# ---------------------------------------------------------------- body site

BODY_SITE_PRIMARY = {
    "feces", "faeces", "fecal", "faecal", "stool", "gut", "intestine",
    "intestinal", "colon", "colonic", "rectal", "rectum", "meconium",
    "ileostomy", "ileum", "jejunum", "small intestine", "large intestine",
    "gastrointestinal tract", "digestive system",
}
BODY_SITE_LINKED = {          # kept, tagged, not primary
    "breast milk", "human milk", "milk", "colostrum", "areola", "nipple",
    "maternal feces", "maternal stool", "vagina", "vaginal", "cervicovaginal",
    "placenta", "amniotic fluid", "cord blood",
}
BODY_SITE_EXCLUDE = {
    "oral", "saliva", "buccal", "tongue", "dental", "plaque", "tooth",
    "skin", "forearm", "forehead", "axilla", "nasal", "nares", "nasopharynx",
    "nasopharyngeal", "oropharynx", "throat", "lung", "bronchoalveolar",
    "sputum", "tracheal", "blood", "serum", "plasma", "urine", "urinary",
    "conjunctiva", "ear", "environmental", "soil", "water", "surface",
}

# ---------------------------------------------------------------- host scope

HOST_INCLUDE = {"homo sapiens", "human", "h. sapiens", "9606"}
HOST_TAXID_INCLUDE = {9606}

# Non-human hosts that masquerade as infant studies. The grant's own example
# (PRJNA716514) was a swine study caught only by reading the linked paper.
HOST_EXCLUDE_PATTERNS = [
    "sus scrofa", "swine", "pig", "piglet", "porcine", "mus musculus", "mouse",
    "mice", "murine", "pup", "rat", "rattus", "macaca", "macaque", "rhesus",
    "marmoset", "baboon", "bos taurus", "cattle", "calf", "bovine", "capra",
    "goat", "kid", "ovis", "sheep", "lamb", "equus", "foal", "canis", "dog",
    "puppy", "felis", "cat", "kitten", "gallus", "chicken", "chick", "danio",
    "zebrafish", "drosophila", "c. elegans", "rabbit", "guinea pig", "hamster",
    "panda", "koala", "bat", "primate infant",
]

# ---------------------------------------------------------- false positives

# "Infantis" is a lexical trap: a Salmonella serovar AND a Bifidobacterium
# subspecies. A live ENA probe returned a Salmonella Infantis study in the
# first three hits of an "infant"-flavored query.
FALSE_POSITIVE_PATTERNS = [
    "salmonella enterica serovar infantis", "salmonella infantis",
    "serovar infantis", "s. infantis",
    "bifidobacterium longum subsp. infantis genome",
    "b. infantis isolate", "infantis strain",
    "lactobacillus", "enterococcus faecalis infantis",
]
SYNTHETIC_DATA_PATTERNS = [
    "simulated", "in silico", "synthetic community", "mock community",
    "mock microbial", "artificial community", "benchmark dataset",
    "camisim", "insilicoseq", "art_illumina", "grinder", "simulated metagenome",
    "spike-in", "standard reference material", "zymobiomics",
]

# ------------------------------------------------------- controlled access

# Not paywalling -- a different, non-remediable failure class.
CONTROLLED_ACCESS_MARKERS = [
    "dbgap", "phs0", "ega", "egad", "egas", "controlled access",
    "data access committee", "dac", "data use agreement", "restricted access",
    "jga", "ddbj japanese genotype", "gsa-human", "hra",
]

# ------------------------------------------------------------- access tiers

ACCESS_TIERS = {
    "A1": "Europe PMC JATS full text retrieved",
    "A2": "Full text + supplementary files retrieved",
    "B1": "Publisher OA PDF retrieved via article-fetch",
    "B2": "Preprint full text retrieved; journal version unreachable",
    "C":  "Abstract only -- curation proceeds with evidence_limited_to=abstract",
    "D":  "No text of any kind reachable",
    "X":  "Controlled-access data (dbGaP/EGA); non-remediable in this sandbox",
}
ABSTRACT_ONLY_TIERS = {"C", "D"}

# ------------------------------------------------- target metadata fields

# The decisive per-sample determinations the grant is built to recover.
TARGET_FIELDS = [
    "probiotic_exposure", "preterm_status", "gestational_age_weeks",
    "delivery_mode", "feeding_mode", "antibiotic_exposure",
    "age_at_collection_days", "birth_weight_grams", "country",
    "maternal_antibiotics", "hmo_supplementation", "nec_status",
]

# -------------------------------------------------------- polite HTTP limits

# NCBI returned 429 within seconds of unthrottled querying from this sandbox.
RATE_LIMITS = {
    "eutils.ncbi.nlm.nih.gov":  {"rps": 2.5, "burst": 1},   # 9.0 with an API key
    "www.ebi.ac.uk":            {"rps": 4.0, "burst": 2},
    "api.crossref.org":         {"rps": 4.0, "burst": 2},
    "api.semanticscholar.org":  {"rps": 1.0, "burst": 1},
    "api.openalex.org":         {"rps": 4.0, "burst": 2},
    "api.biorxiv.org":          {"rps": 2.0, "burst": 1},
    "pmc.ncbi.nlm.nih.gov":     {"rps": 2.5, "burst": 1},
    "_default":                 {"rps": 2.0, "burst": 1},
}
NCBI_RPS_WITH_KEY = 9.0


# --------------------------------------------- exclusion reason vocabulary
# Controlled. Every exclusion row must carry one of these; free text goes in
# reason_detail. Published in CATALOG_REPORT so the catalog is auditable.

REASON_CODES = {
    "assay_amplicon":          "Amplicon (16S/18S/ITS or other marker gene), not shotgun",
    "assay_amplicon_misfiled": "Filed as WGS/OTHER but carries amplicon tells (target_gene, primers)",
    "assay_rna":               "Metatranscriptomic / RNA-seq",
    "assay_isolate_genome":    "Cultured isolate genome (library_source=GENOMIC), not a metagenome",
    "assay_other_nonshotgun":  "Some other non-shotgun assay",
    "assay_assembly_only":     "Assembly/MAG deposit with no underlying in-scope reads",
    "host_nonhuman":           "Non-human host (animal model)",
    "host_environmental":      "Environmental sample, no human host",
    "host_synthetic":          "Simulated, mock, or synthetic community",
    "age_adult_only":          "Human but no subjects aged 0-36 months",
    "age_child_over_36m":      "Paediatric but all subjects older than 36 months",
    "age_maternal_only":       "Maternal/pregnancy samples with no infant samples",
    "age_unknown_no_evidence": "No age evidence anywhere in archive record or paper",
    "site_excluded":           "Body site outside gut and the retained linked sites",
    "site_unknown":            "Body site not determinable",
    "fp_salmonella_infantis":  "Salmonella enterica serovar Infantis (name collision)",
    "fp_bifido_infantis":      "B. longum subsp. infantis strain genomics (name collision)",
    "fp_name_only":            "'Infant' appears only in a strain, sample, or project name",
    "access_controlled":       "Controlled-access repository (dbGaP/EGA/GSA-Human/JGA)",
    "access_suppressed":       "Record suppressed or withdrawn by the archive",
    "dup_mirror":              "Duplicate of another archive's mirror of the same study",
    "dup_reanalysis":          "Re-deposit of data already catalogued under another accession",
}

TRIAGE_VERDICTS = {"include", "exclude", "uncertain"}


# ------------------------------------------------- ENA harvest field sets
# Verified present in the ENA portal searchFields inventory on 2026-09-14
# (read_run/read_study expose 160 fields; sample exposes 95).

# Run-level: identity, assay, and the technical covariates that replace 16S
# hypervariable region as the harmonization axis now that amplicon is out.
ENA_RUN_FIELDS = [
    "run_accession", "experiment_accession", "sample_accession",
    "secondary_sample_accession", "study_accession", "secondary_study_accession",
    "submission_accession", "run_alias", "experiment_alias", "sample_alias",
    "study_alias", "project_name", "secondary_project",
    # assay classification
    "library_strategy", "library_source", "library_selection", "library_layout",
    "library_name", "target_gene", "investigation_type", "sequencing_method",
    # technical covariates
    "instrument_platform", "instrument_model", "read_count", "base_count",
    "nominal_length", "nominal_sdev", "submitted_read_type", "submitted_format",
    "library_construction_protocol", "library_gen_protocol", "extraction_protocol",
    "pcr_isolation_protocol", "library_prep_date",
    # assembly-derived deposits
    "assembly_software", "binning_software", "completeness_score", "contamination_score",
    # host / subject
    "host", "host_scientific_name", "host_tax_id", "host_body_site", "host_sex",
    "host_status", "host_phenotype", "host_genotype", "host_gravidity",
    "age", "dev_stage", "sex", "submitted_host_sex", "disease",
    # organism / false-positive detection
    "tax_id", "scientific_name", "strain", "sub_species", "sub_strain",
    "serovar", "serotype", "isolate", "environmental_sample",
    # context
    # NOTE: collection_date is NOT an ENA portal field on any result type; it
    # arrives only as a sample XML attribute, so it lands in sample_attributes.
    "country", "location", "collected_by", "isolation_source",
    "environmental_medium", "environment_material", "sample_collection",
    "sample_storage", "sample_storage_processing", "checklist",
    "experimental_factor", "description", "sample_description", "sample_title",
    "study_title", "center_name", "broker_name", "first_public", "first_created",
    "last_updated", "status", "tag",
]

ENA_STUDY_FIELDS = [
    "study_accession", "secondary_study_accession", "study_title", "study_alias",
    "description", "center_name", "broker_name", "first_public", "last_updated",
    "tax_id", "scientific_name", "project_name", "status",
]

ENA_SAMPLE_FIELDS = [
    "sample_accession", "secondary_sample_accession", "sample_alias",
    "sample_title", "sample_description", "description", "tax_id",
    "scientific_name", "host", "host_scientific_name", "host_tax_id",
    "host_body_site", "host_sex", "host_status", "host_phenotype",
    "age", "dev_stage", "sex", "disease", "country", "location",
    "collected_by", "isolation_source", "environmental_medium",
    "sample_collection", "checklist", "keywords",
    "strain", "sub_species", "serovar", "isolate", "environmental_sample",
    "first_public", "last_updated", "status",
]

# Amplicon tells: a run carrying any of these is amplicon regardless of how
# library_strategy is filled in. This is the mislabel audit's primary test.
AMPLICON_TELL_FIELDS = ["target_gene", "pcr_isolation_protocol"]
AMPLICON_TELL_VALUES = [
    "16s", "16 s", "18s", "its", "its1", "its2", "23s", "rrna", "rrs",
    "v1-v2", "v1-v3", "v3-v4", "v4", "v4-v5", "v6", "v6-v8", "amplicon",
    "515f", "806r", "27f", "338f", "341f", "785r", "926r", "1492r", "gyrb",
    "cpn60", "rpob", "amoa", "nifh",
]
# Short reads with tiny totals are the secondary signature of misfiled amplicon.
AMPLICON_BASECOUNT_SUSPICION = 500_000_000   # < 0.5 Gbp per run is suspicious for WGS


def strategy_verdict(library_strategy: str):
    """Return 'include' | 'adjudicate' | 'exclude' for an ENA library_strategy."""
    s = (library_strategy or "").strip()
    if s in LIBRARY_STRATEGY_INCLUDE:
        return "include"
    if s in LIBRARY_STRATEGY_ADJUDICATE:
        return "adjudicate"
    return "exclude"


def source_verdict(library_source: str):
    """Return 'include' | 'side_table' | 'exclude' for an ENA library_source."""
    s = (library_source or "").strip().upper()
    if s in LIBRARY_SOURCE_INCLUDE:
        return "include"
    if s in LIBRARY_SOURCE_SIDE_TABLE:
        return "side_table"
    return "exclude"


def ena_shotgun_clause():
    """ENA portal query fragment restricting to in-scope DNA shotgun libraries."""
    strat = " OR ".join(f'library_strategy="{s}"' for s in sorted(LIBRARY_STRATEGY_INCLUDE))
    return f'library_source="METAGENOMIC" AND ({strat})'


def ena_taxon_clause(taxa=None):
    """ENA portal query fragment covering the enumeration frame taxa."""
    taxa = taxa or TAXA_ALL_FRAME
    return "(" + " OR ".join(f"tax_eq({t})" for t in sorted(taxa)) + ")"

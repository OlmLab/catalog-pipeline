"""gapfill_samples / apply_gapfill tests.

(a) synthetic 5-run slice: no network — the harvest is monkeypatched with a fixed attribute table; exercises the
    R1 field-map parsers, the U3 unit rule, composite subject ids, validate_all (out_of_scope_adult convention),
    sentinels, body-site classification and the wide/subject builders against a 2-row synthetic package;
(b) apply_gapfill on the synthetic package: row counts, no-existing-row-change proof, study/universe/build_counts updates;
(c) real-run smoke on the R2026.2 PRJNA1140720 outputs when CATALOG_GAPFILL_DIR points at them (skipped otherwise).
"""
import json
import os
import sys

import numpy as np
import pandas as pd
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in ("src", "src/catalog", "src/catalog/extraction", "src/catalog/release", "src/catalog/harvest", "src/catalog/enumeration", "src/catalog/triage", "src/catalog/sandpiper"):
    sys.path.insert(0, os.path.join(REPO, p))
import gapfill_samples as GF  # noqa: E402
import apply_gapfill as AG  # noqa: E402

STUDY = "PRJNA0000001"
FM = os.path.join(REPO, "config", "attribute_field_map.csv")
WIDE_COLS_FILE = os.path.join(REPO, "tests", "data", "wide_columns_1.3.0.json")


def _wide_cols():
    return json.load(open(WIDE_COLS_FILE))


def _synthetic_package(tmp):
    """2 existing samples (an infant and its mother) with package-shaped tables (only the columns the code touches, plus the
    full 148-column wide layout)."""
    pkg = os.path.join(tmp, "pkg"); os.makedirs(pkg)
    cols = _wide_cols()
    runs = pd.DataFrame([dict(run_accession="SRR1", study_accession=STUDY, sample_accession="SAMN1", secondary_sample_accession="SRS1", experiment_accession="SRX1",
                              library_strategy="WGS", library_source="METAGENOMIC", library_layout="PAIRED", library_name="X_F1_BA100_T01_F", instrument_platform="ILLUMINA",
                              instrument_model="Illumina NovaSeq 6000", read_count="1000", base_count="150000", scientific_name="human gut metagenome", first_public="2025-01-01", sample_title="t", country="Italy"),
                         dict(run_accession="SRR2", study_accession=STUDY, sample_accession="SAMN2", secondary_sample_accession="SRS2", experiment_accession="SRX2",
                              library_strategy="WGS", library_source="METAGENOMIC", library_layout="PAIRED", library_name="X_F1_MO101_T01_F", instrument_platform="ILLUMINA",
                              instrument_model="Illumina NovaSeq 6000", read_count="1000", base_count="150000", scientific_name="human gut metagenome", first_public="2025-01-01", sample_title="t", country="Italy")])
    for c in ("secondary_study_accession", "library_selection", "target_gene", "nominal_length", "tax_id", "host_tax_id", "host_scientific_name", "host_body_site", "host_status", "host_phenotype", "age", "dev_stage", "disease", "center_name", "project_name", "study_title", "serovar", "sub_species", "strain", "isolate", "checklist", "environmental_medium", "isolation_source", "experimental_factor", "extraction_protocol", "environmental_sample", "found_by"):
        runs[c] = None
    runs.to_parquet(os.path.join(pkg, "runs.parquet"), index=False)
    wide = pd.DataFrame({c: [None, None] for c in cols})
    wide["sample_key"] = ["SAMN1", "SAMN2"]; wide["study_accession"] = STUDY; wide["body_site_class"] = "primary"; wide["role"] = ["infant", "mother"]
    wide["role_source"] = "attr_role"; wide["age_scope"] = ["age_unknown_no_study_estimate", "non_infant_role"]; wide["catalog_scope"] = False; wide["adult_age_flag"] = False
    wide["sp_profiled"] = False; wide["study_title"] = "Synthetic"; wide["cohort_id"] = "COH9999"; wide["cohort_name"] = "Synthetic 2026"; wide["first_public_min"] = "2025-01-01"
    wide["sample_unit"] = "biosample"; wide["n_fields_with_value"] = 0
    wide.to_parquet(os.path.join(pkg, "sample_metadata_wide.parquet"), index=False)
    det = pd.DataFrame([dict(sample_key="SAMN1", field_name="subject_id", study_accession=STUDY, field_value="F1_BA100", value_normalized="F1_BA100", confidence=0.85,
                             evidence_source="biosample_attr", evidence_locator="subject_id", evidence_quote="F1_BA100", evidence_limited_to_abstract=0.0, determined_by="deterministic_r1",
                             route="R1", scope="sample", parse_note="identifier", group_audit=None, src_track="phase2", release_added="1.0.0", release_retired=None, package_added="1.0.0")])
    det.to_parquet(os.path.join(pkg, "sample_determinations.parquet"), index=False)
    det.assign(retired_reason=None, retired_change_stage=None).to_parquet(os.path.join(pkg, "sample_determinations_all.parquet"), index=False)
    subj = pd.DataFrame([dict(sample_key="SAMN1", study_accession=STUDY, subject_key=f"{STUDY}|F1_BA100", subject_id_resolved="F1_BA100", role="infant", role_source="attr_role", subject_source="det_subject_id_R1",
                              linked_infant_subject_key=None, t_index=1.0, n_timepoints_subject=1.0, t_basis="single_sample", age_days_used=None, age_source=None, timepoint_label="T01", sample_unit="biosample", parent_biosample=None, age_scope="age_unknown_no_study_estimate"),
                         dict(sample_key="SAMN2", study_accession=STUDY, subject_key=f"{STUDY}|F1_MO101", subject_id_resolved="F1_MO101", role="mother", role_source="attr_role", subject_source="det_subject_id_R1",
                              linked_infant_subject_key=f"{STUDY}|F1_BA100", t_index=1.0, n_timepoints_subject=1.0, t_basis="single_sample", age_days_used=None, age_source=None, timepoint_label="T01", sample_unit="biosample", parent_biosample=None, age_scope="non_infant_role")])
    subj.to_parquet(os.path.join(pkg, "sample_subjects.parquet"), index=False)
    smw = pd.DataFrame([dict(study_accession=STUDY, n_samples=2, n_runs=2, n_biosamples=2, n_sample_rows=2, n_infant_scope_samples=2, n_body_site_excluded=0, n_catalog_scope=0, n_age_scope_infant=0,
                             n_adult_flagged=0, n_non_infant_role=1, n_infant_evidenced=0, n_study_all_infant=0, n_age_unknown_mixed_study=0, n_age_unknown_no_study_estimate=1, n_mothers=1,
                             n_infant_role_samples=1, n_infant_samples_est=np.nan, sp_n_samples_profiled=0, sp_frac_samples_profiled=0.0, sp_n_runs_profiled=0, sp_frac_runs_profiled=0.0,
                             **{f"cov_{f}": 0.0 for f in GF.TARGET_FIELDS}),
                        dict(study_accession="PRJNA0000002", n_samples=5, n_runs=5, n_biosamples=5, n_sample_rows=5, n_infant_scope_samples=5, n_body_site_excluded=0, n_catalog_scope=5, n_age_scope_infant=5,
                             n_adult_flagged=0, n_non_infant_role=0, n_infant_evidenced=5, n_study_all_infant=0, n_age_unknown_mixed_study=0, n_age_unknown_no_study_estimate=0, n_mothers=0,
                             n_infant_role_samples=5, n_infant_samples_est=5.0, sp_n_samples_profiled=0, sp_frac_samples_profiled=0.0, sp_n_runs_profiled=0, sp_frac_runs_profiled=0.0,
                             **{f"cov_{f}": 0.0 for f in GF.TARGET_FIELDS})])
    smw.to_parquet(os.path.join(pkg, "study_metadata_wide.parquet"), index=False); smw.to_csv(os.path.join(pkg, "study_metadata_wide.csv"), index=False)
    spq = pd.DataFrame([dict(run_accession="SRR1", study_accession=STUDY, sample_accession="SAMN1", catalog_sample_key="SAMN1", sample_unit="biosample", in_sandpiper=False, sp_miss_reason="sra_illumina_not_in_snapshot",
                             library_strategy="WGS", library_source="METAGENOMIC", instrument_platform="ILLUMINA", base_count=150000.0, first_public=pd.Timestamp("2025-01-01"), organism="human gut metagenome",
                             sp_root_coverage=np.nan, sp_warning_present=False, sp_flag_non_metagenome_strict=False, sp_flag_non_metagenome_loose=False, sp_nonmeta_class="not_flagged", sp_flag_synthetic=False,
                             sp_flag_rna_strict=False, sp_flag_rna_loose=False, sandpiper_url=None, sandpiper_version="2.0.0", taxonomy_db="GTDB", taxonomy_version="R232", zenodo_record="20419175",
                             release_added="1.2.0", release_retired=None, package_added="1.2.0")])
    spq.to_parquet(os.path.join(pkg, "sandpiper_run_qc.parquet"), index=False)
    sps_cols = ["sample_key", "sp_n_runs_profiled", "sp_spf", "sp_known_species_fraction", "sp_flag_low_complexity", "sp_flag_non_metagenome", "sp_flag_synthetic", "sp_flag_rna", "sp_flag_readfraction_warning", "sandpiper_url", "sp_runs_profiled",
                "sp_n_runs_total", "sp_partial", "sp_root_coverage", "sp_low_depth", "sp_profiled", "sp_run_concordance_bc", "sp_runs_discordant", "sp_ra_g_Bifidobacterium", "sp_top_genus", "sp_top_genus_ra", "sp_shannon_genus",
                "sp_n_genera_ge1pct", "taxonomy_db", "taxonomy_version", "sandpiper_version", "zenodo_record", "sp_nonmeta_class", "release_added", "release_retired", "package_added"]
    pd.DataFrame(columns=sps_cols).to_parquet(os.path.join(pkg, "sandpiper_sample_summary.parquet"), index=False)
    pd.DataFrame([dict(study_accession=STUDY, pmid=None, pmcid=None, doi=None, title=None)]).to_csv(os.path.join(pkg, "study_paper_links.csv"), index=False)
    pd.DataFrame([dict(study_accession=STUDY, n_samples=2, n_runs=2), dict(study_accession="PRJNA0000002", n_samples=5, n_runs=5)]).to_parquet(os.path.join(pkg, "universe_studies_all.parquet"), index=False)
    json.dump(dict(n_samples=2, n_runs=2, n_biosample_units=2, n_determinations_current=1, n_determinations_all=1, n_body_site_excluded=0, n_profiled_samples=0), open(os.path.join(pkg, "build_counts.json"), "w"))
    return pkg


def _synthetic_new_runs(tmp):
    rows = []
    spec = [("SRR11", "SAMN11", "X_F1_MO101_T02_O", "SRX11"), ("SRR12", "SAMN12", "X_F1_MO101_T03_O", "SRX12"), ("SRR13", "SAMN13", "X_F1_FA102_T01_O", "SRX13"),
            ("SRR14", "SAMN14", "X_F1_SI103_T01_O", "SRX14"), ("SRR15", "SAMN15", "X_F1_BA100_T02_F", "SRX15")]
    for r, s, lib, x in spec:
        rows.append(dict(run_accession=r, study_accession=STUDY, sample_accession=s, secondary_sample_accession="S" + r, experiment_accession=x, library_strategy="WGS", library_source="METAGENOMIC",
                         library_layout="PAIRED", library_name=lib, instrument_platform="ILLUMINA", instrument_model="Illumina NovaSeq 6000", read_count="0", base_count="0",
                         scientific_name="human saliva metagenome" if lib.endswith("_O") else "human gut metagenome", first_public="2026-09-02", sample_title="Metagenome sample", country=None))
    nr = pd.DataFrame(rows)
    for c in ("secondary_study_accession", "library_selection", "target_gene", "nominal_length", "tax_id", "host_tax_id", "host_scientific_name", "host_body_site", "host_status", "host_phenotype", "age", "dev_stage", "disease", "center_name", "project_name", "study_title", "serovar", "sub_species", "strain", "isolate", "checklist", "environmental_medium", "isolation_source", "experimental_factor", "extraction_protocol", "environmental_sample", "found_by"):
        nr[c] = None
    p = os.path.join(tmp, "new_runs.parquet"); nr.to_parquet(p, index=False)
    return p


def _synthetic_attrs():
    A = {"SAMN11": dict(subjectid="MO101", family_id="F1", participant_type="Mother", age="36", sex="female", timepoint="T02", isolation_source="saliva", sample_type="oral", geo_loc_name="Italy"),
         "SAMN12": dict(subjectid="MO101", family_id="F1", participant_type="Mother", age="36", sex="female", timepoint="T03", isolation_source="saliva", sample_type="oral", geo_loc_name="Italy"),
         "SAMN13": dict(subjectid="FA102", family_id="F1", participant_type="Father", age="40", sex="male", timepoint="T01", isolation_source="saliva", sample_type="oral", geo_loc_name="Italy"),
         "SAMN14": dict(subjectid="SI103", family_id="F1", participant_type="Sibling", age="2", sex="female", timepoint="T01", isolation_source="saliva", sample_type="oral", geo_loc_name="Italy"),
         "SAMN15": dict(subjectid="BA100", family_id="F1", participant_type="Baby", age="14", sex="male", timepoint="T02", isolation_source="feces", sample_type="Fecal", geo_loc_name="Italy")}
    rows = [(sk, k, k, v, None, "ena_sample_xml") for sk, d in A.items() for k, v in d.items()]
    return pd.DataFrame(rows, columns=["sample_key", "attr_key", "attr_key_norm", "value", "attr_units", "source"])


def _supp_sheet():
    # per-individual table: participant_id + age_months (+ participant_type corroboration)
    hdr = ["participant_id", "participant_type", "age_months", "family_id"]
    body = [["100", "Baby", "14", "F1"], ["101", "Mother", "432", "F1"], ["102", "Father", "486", "F1"], ["103", "Sibling", "27", "F1"]] + [[str(200 + i), "Mother", str(400 + i), f"F{i}"] for i in range(30)]
    return pd.DataFrame([hdr] + body)


@pytest.fixture()
def synthetic(tmp_path, monkeypatch):
    pkg = _synthetic_package(str(tmp_path)); nr = _synthetic_new_runs(str(tmp_path))
    attrs = _synthetic_attrs()
    monkeypatch.setattr(GF, "harvest", lambda study, new_runs, purpose="x": (attrs, pd.DataFrame(), {"title": "Synthetic"}, dict(n_samples=5, n_found=5, n_ena=5, n_ncbi=0, n_missing=0, n_ena_batches_err=0, n_attr_rows=len(attrs), n_experiments=0)))
    sheets = {("supp.xlsx", "ST3"): _supp_sheet()}
    gate = pd.DataFrame([dict(pmcid="PMC0", file="supp.xlsx", sheet="ST3", n_rows=35, n_cols=4, n_exact_id_hits=0, frac_new_ids_hit=0.0, passes_exact_gate=False, is_matrix=False, header_named_field_columns="", r2_usable=False)])
    monkeypatch.setattr(GF, "r2_gate", lambda study, pkg_, new_runs, purpose="x": (gate, sheets))
    out = str(tmp_path / "gapfill")
    res = GF.run(STUDY, nr, pkg, out, "R2026.2", "1.4.0", FM, sandpiper=False, harvest_existing_flag=False)
    return dict(pkg=pkg, out=out, res=res, tmp=str(tmp_path))


def test_r1_fields_and_unit_rule(synthetic):
    det = synthetic["res"]["det"]
    assert set(det.field_name) == {"country", "sex", "timepoint_label", "subject_id", "age_at_collection_days"}
    assert det.groupby("field_name").size().to_dict() == {"country": 5, "sex": 5, "timepoint_label": 5, "subject_id": 5, "age_at_collection_days": 4}
    ages = det[det.field_name == "age_at_collection_days"].set_index("sample_key").value_normalized.astype(int)
    assert ages["SAMN14"] == round(2 * 365.25) and ages["SAMN13"] == round(40 * 365.25)
    # U3 adopted years: the paper table (age_months) agrees with the bare attribute
    assert det[det.field_name == "age_at_collection_days"].parse_note.str.contains("U3:years").all()
    oos = det[det.parse_note.str.startswith("out_of_scope_adult")]
    assert set(oos.sample_key) == {"SAMN11", "SAMN12", "SAMN13"} and synthetic["res"]["meta"]["n_out_of_scope_adult"] == 3
    # every committed row carries a labelled source and passed the validator
    assert det.evidence_source.str.startswith(("sample.attr.", "run.", "paper.supp.", "sample_id_pattern")).all()
    assert synthetic["res"]["meta"]["validator_pass_rate"] == 1.0
    # mixed-unit trap: the baby's bare '14' (months, per the paper table) disagrees with the study-level unit 'years' ->
    # per-sample corroboration leaves it a sentinel instead of committing 14 years
    assert "SAMN15" not in ages.index
    rejected = pd.read_parquet(os.path.join(synthetic["out"], "sample_determinations_rejected_new.parquet"))
    assert rejected.sample_key.tolist() == ["SAMN15"] and rejected.reject_reason.str.contains("disagrees with the paper table").all()
    sent = synthetic["res"]["sentinels"]
    assert ((sent.record_id == "SAMN15") & (sent.slot == "age_at_collection_days")).sum() == 1


def test_composite_subject_and_subjects(synthetic):
    det = synthetic["res"]["det"]; sj = synthetic["res"]["subjects"]
    sid = det[det.field_name == "subject_id"].set_index("sample_key").value_normalized
    assert sid["SAMN11"] == "F1_MO101" and sid["SAMN15"] == "F1_BA100"
    s = sj.set_index("sample_key")
    assert s.loc["SAMN11", "subject_key"] == f"{STUDY}|F1_MO101" and s.loc["SAMN11", "role"] == "mother" and s.loc["SAMN11", "role_source"] == "attr_role"
    assert s.loc["SAMN13", "role"] == "other" and s.loc["SAMN14", "role"] == "other"
    assert s.loc["SAMN11", "linked_infant_subject_key"] == f"{STUDY}|F1_BA100"   # joined from the existing subjects
    assert s.loc["SAMN11", "n_timepoints_subject"] == 2 and s.loc["SAMN11", "t_basis"] == "timepoint_label"  # year-granular ages do not order timepoints


def test_wide_scope_and_sentinels(synthetic):
    w = synthetic["res"]["wide"].set_index("sample_key")
    assert list(synthetic["res"]["wide"].columns) == _wide_cols()
    assert w.loc["SAMN11", "body_site_class"] == "excluded" and w.loc["SAMN15", "body_site_class"] == "primary"
    assert w.loc["SAMN11", "age_scope"] == "adult_flagged" and bool(w.loc["SAMN11", "adult_age_flag"])
    assert w.loc["SAMN14", "age_scope"] == "non_infant_role"          # role precedence over infant age, as documented
    assert not w.catalog_scope.astype(bool).any()
    sent = synthetic["res"]["sentinels"]
    assert len(sent) == 5 * len(GF.ALL_FIELDS) - len(synthetic["res"]["det"]) and (sent.outcome == "sentinel_no_evidence").all()
    assert os.path.exists(os.path.join(synthetic["out"], f"GAPFILL_{STUDY}_REPORT.md"))
    qc = synthetic["res"]["run_qc"]
    assert (qc.sp_miss_reason == "not_in_snapshot_api_unavailable").all() and (~qc.in_sandpiper).all()


def test_apply_gapfill_no_existing_row_changes(synthetic):
    pkg, out = synthetic["pkg"], synthetic["out"]
    before = {f: pd.read_parquet(os.path.join(pkg, f)) for f in ("runs.parquet", "sample_metadata_wide.parquet", "sample_determinations.parquet", "sample_subjects.parquet")}
    applied = os.path.join(synthetic["tmp"], "applied")
    rep = AG.apply(pkg, out, applied)
    for f, old in before.items():
        new = pd.read_parquet(os.path.join(applied, f))
        assert len(new) == len(old) + rep["tables"][f]["added"]
        a = new.iloc[:len(old)].reset_index(drop=True).astype(object); b = old.reset_index(drop=True).astype(object)
        pd.testing.assert_frame_equal(a.where(a.notna(), None), b.where(b.notna(), None), check_dtype=False)
    assert rep["tables"]["sample_determinations.parquet"]["added"] == 24 and rep["tables"]["runs.parquet"]["added"] == 5
    sm = pd.read_parquet(os.path.join(applied, "study_metadata_wide.parquet")).set_index("study_accession")
    assert sm.loc[STUDY, "n_samples"] == 7 and sm.loc[STUDY, "n_runs"] == 7 and sm.loc["PRJNA0000002", "n_samples"] == 5
    assert sm.loc[STUDY, "n_adult_flagged"] == 3 and sm.loc[STUDY, "n_body_site_excluded"] == 4
    ua = pd.read_parquet(os.path.join(applied, "universe_studies_all.parquet")).set_index("study_accession")
    assert ua.loc[STUDY, "n_samples"] == 7 and ua.loc["PRJNA0000002", "n_runs"] == 5
    bc = json.load(open(os.path.join(applied, "build_counts.json")))
    assert bc["n_samples"] == 7 and bc["n_determinations_current"] == 25 and bc["gapfill"][0]["study"] == STUDY
    # applying twice must refuse (keys already present)
    with pytest.raises(AssertionError):
        AG.apply(applied, out, os.path.join(synthetic["tmp"], "applied2"))


# ------------------------------------------------------------------------------------------------ real-run smoke
GAP = os.environ.get("CATALOG_GAPFILL_DIR", os.path.join(REPO, "build", "gapfill_R2026.2"))


@pytest.mark.skipif(not os.path.exists(os.path.join(GAP, "samples_new_wide.parquet")), reason="R2026.2 gapfill outputs not present")
def test_real_run_smoke():
    w = pd.read_parquet(os.path.join(GAP, "samples_new_wide.parquet")); det = pd.read_parquet(os.path.join(GAP, "sample_determinations_new.parquet"))
    sj = pd.read_parquet(os.path.join(GAP, "sample_subjects_new.parquet")); qc = pd.read_parquet(os.path.join(GAP, "sandpiper_run_qc_new.parquet"))
    summ = json.load(open(os.path.join(GAP, "gapfill_summary.json")))
    assert list(w.columns) == _wide_cols() and len(w) == 150 and w.sample_key.is_unique
    assert (w.study_accession == "PRJNA1140720").all() and (w.body_site_class == "excluded").all() and not w.catalog_scope.astype(bool).any()
    assert len(det) == 749 and (det.release_added == "R2026.2").all() and (det.package_added == "1.4.0").all() and det.release_retired.isna().all()
    assert det.field_name.value_counts().to_dict() == {"country": 150, "sex": 150, "subject_id": 150, "timepoint_label": 150, "age_at_collection_days": 149}
    assert det.evidence_source.str.startswith(("sample.attr.", "run.", "paper.supp.")).all() and det.evidence_quote.str.split().str.len().le(12).all()
    assert summ["meta"]["validator_pass_rate"] == 1.0 and summ["meta"]["n_out_of_scope_adult"] == 145
    assert set(sj.sample_key) == set(w.sample_key) and sj.subject_key.notna().all()
    assert len(qc) == 150 and (~qc.in_sandpiper).all() and set(qc.sp_miss_reason) == {"published_after_snapshot_horizon"}

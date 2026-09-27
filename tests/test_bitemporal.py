"""R2026.1 bitemporal invariants (docs/RELEASES.md §3, config/releases.yaml).

Two layers: (a) a synthetic 3-row package that always runs, (b) the real 1.2.2 package under
data/inputs/data_package (or CATALOG_PACKAGE_DIR) — skipped when absent. The retired-row RULE under test:
a value_history row is a retired published value iff status ∈ retired_statuses
(superseded, moved_to_parent_biosamples, recommitted_out_of_scope_host, recommitted_out_of_scope_isolate).
"""
import os
import re
import sys

import pandas as pd
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "src"))
from catalog.release import bitemporal as bt  # noqa: E402

PKG = os.environ.get("CATALOG_PACKAGE_DIR", os.path.join(REPO, "data", "inputs", "data_package"))
CFG = bt.load_config()
RID, PV, PREV = "R2026.1", "1.3.0", "1.2.2"          # the first numbered release (reconstruction mode)
LAST = bt.release_order(CFG)[-1]                       # newest declared release (R2026.2 → incremental mode from a 1.3.0 package)


def _has_pkg():
    return os.path.exists(os.path.join(PKG, "sample_determinations.parquet")) and os.path.exists(os.path.join(PKG, "value_history.parquet"))


def _pkg_is_bitemporal():
    import pyarrow.parquet as pq
    return _has_pkg() and "release_added" in pq.ParquetFile(os.path.join(PKG, "sample_determinations.parquet")).schema_arrow.names


def _run_args():
    """(release_id, package_version, previous_version) for bt.run on the unpacked package: reconstruction from a 1.2.2 package,
    incremental from a package that already carries the release columns (its VERSION.json names the previous release)."""
    if not _pkg_is_bitemporal():
        return RID, PV, PREV
    import json as _j
    v = _j.load(open(os.path.join(PKG, "VERSION.json")))
    prev_pv = v["package_version"]
    nxt = next((r for r in CFG["releases"] if r["previous_package_version"] == prev_pv), None)
    assert nxt, f"config/releases.yaml has no release following package {prev_pv}"
    return nxt["release_id"], nxt["package_version"], prev_pv


# ------------------------------------------------------------------------------------------------ config
def test_config_ids_and_columns():
    assert re.match(CFG["release_id"]["regex"], RID)
    assert not re.match(CFG["release_id"]["regex"], "1.2.2")
    assert [h["id"] for h in CFG["history"]] == ["1.0.0", "1.1.0", "1.2.0", "1.2.1", "1.2.2"]
    assert bt.release_order(CFG)[-1] == LAST and bt.package_of(CFG, RID) == PV and bt.package_of(CFG, "R2026.2") == "1.4.0"
    rel = {r["release_id"]: r for r in CFG["releases"]}
    assert rel["R2026.2"]["previous_release_id"] == "R2026.1" and rel["R2026.2"]["previous_package_version"] == "1.3.0"
    assert tuple(CFG["columns"][c] for c in ("release_added", "release_retired", "package_added")) == bt.COLS
    assert {t["file"] for t in CFG["fact_tables"]} >= {"sample_determinations.parquet", "universe_studies_all.parquet", "cohorts.csv",
                                                       "study_paper_links.csv", "sandpiper_sample_summary.parquet", "sandpiper_run_qc.parquet",
                                                       "sandpiper_top_genera.parquet", "sandpiper_study_panels.parquet", "study_metadata_wide.parquet"}
    assert "sample_metadata_wide.parquet" not in {t["file"] for t in CFG["fact_tables"]}  # derived table: no release columns
    # every change_stage maps to a declared release id
    ids = set(bt.release_order(CFG))
    assert set(CFG["change_stage_to_package"].values()) <= ids and set(CFG["src_track_to_package"].values()) <= ids


# ------------------------------------------------------------------------------------------------ synthetic
def _synthetic(tmp_path):
    d = tmp_path / "pkg"
    d.mkdir()
    cols = ["sample_key", "field_name", "study_accession", "field_value", "value_normalized", "confidence", "evidence_source",
            "evidence_locator", "evidence_quote", "evidence_limited_to_abstract", "determined_by", "route", "scope", "parse_note",
            "group_audit", "src_track"]
    sd = pd.DataFrame([["S1", "age_at_collection_days", "PRJ1", "5", "5", 0.9, "biosample_attr", "age", "age=5", 0.0, "r1", "R1", "sample", None, None, "phase2"],
                       ["S2", "age_at_collection_days", "PRJ1", "40", "14600", 0.9, "biosample_attr", "age", "age=40", 0.0, "r1", "R1", "sample", None, None, "adult_scope_fix"],
                       ["R1", "sex", "PRJ1", "F", "female", 0.8, "biosample_attr", "sex", "sex=F", 0.0, "r1", "R1", "sample", None, None, "sample_unit_fix"]], columns=cols)
    sd.to_parquet(d / "sample_determinations.parquet", index=False)
    vh = pd.DataFrame([dict(sample_key="S2", field_name="age_at_collection_days", study_accession="PRJ1", field_value="40", value_normalized="14600.0",
                            status="recommitted_out_of_scope_adult", reason="age outside 0-1100", replaced_by="current", change_stage="auditor_review:B9"),
                       dict(sample_key="S3", field_name="sex", study_accession="PRJ1", field_value="M", value_normalized="male",
                            status="superseded", reason="per-stool value collapsed", replaced_by="run-level", change_stage="sample_unit_fix"),
                       dict(sample_key="S9", field_name="age_at_collection_days", study_accession="PRJ1", field_value="x", value_normalized=None,
                            status="rejected", reason="unparseable", replaced_by=None, change_stage="r1_parse")])
    vh.to_parquet(d / "value_history.parquet", index=False)
    pd.DataFrame({"sample_key": ["S1", "S2", "R1"], "catalog_scope": [True, False, True]}).to_parquet(d / "sample_metadata_wide.parquet", index=False)
    pd.DataFrame({"study_accession": ["PRJ1"], "triage_verdict": ["include"]}).to_parquet(d / "study_metadata_wide.parquet", index=False)
    pd.DataFrame({"study_accession": ["PRJ1", "PRJ2"], "triage_verdict": ["include", "exclude"]}).to_parquet(d / "universe_studies_all.parquet", index=False)
    pd.DataFrame({"cohort_id": ["COH0001"], "cohort_name": ["a"]}).to_csv(d / "cohorts.csv", index=False)
    return str(d)


def test_synthetic_seeding_and_history(tmp_path):
    pkg = _synthetic(tmp_path)
    out = str(tmp_path / "out")
    log = bt.run(pkg, out, RID, PV, PREV, previous_package=None, release_date="2026-09-26")
    sd = pd.read_parquet(os.path.join(out, "sample_determinations.parquet"))
    assert list(sd.columns[-3:]) == list(bt.COLS)
    assert sd["release_added"].tolist() == ["1.0.0", "1.2.0", "1.1.0"]  # default / B9+adult_scope_fix / sample_unit_fix
    assert sd["package_added"].tolist() == ["1.0.0", "1.2.0", "1.1.0"] and sd["release_retired"].isna().all()
    allrows = pd.read_parquet(os.path.join(out, "sample_determinations_all.parquet"))
    cur, ret = allrows[allrows["release_retired"].isna()], allrows[allrows["release_retired"].notna()]
    assert len(cur) == 3 and len(ret) == 1  # the rejected r1_parse row was never published → not a retired row
    assert ret.iloc[0]["release_retired"] == "1.1.0" and ret.iloc[0]["retired_change_stage"] == "sample_unit_fix"
    assert ret.iloc[0]["retired_reason"] == "per-stool value collapsed"
    reg = pd.read_csv(os.path.join(out, "releases.csv"), dtype=str, keep_default_na=False)
    assert reg["release_id"].tolist() == ["1.0.0", "1.1.0", "1.2.0", "1.2.1", "1.2.2", RID]
    assert reg.iloc[-1][["n_studies_included", "n_samples", "n_catalog_scope", "n_determinations_current"]].tolist() == ["1", "3", "2", "3"]
    assert log["counts"]["n_determinations_current"] == 3
    coh = pd.read_csv(os.path.join(out, "cohorts.csv"), dtype=str, keep_default_na=False)
    assert coh["release_added"].tolist() == ["1.0.0"] and coh["release_retired"].tolist() == [""]


def test_synthetic_new_and_gone_rows_against_previous(tmp_path):
    prev = _synthetic(tmp_path)
    new_dir = tmp_path / "new"
    import shutil
    shutil.copytree(prev, new_dir)
    sd = pd.read_parquet(os.path.join(prev, "sample_determinations.parquet"))
    sd = pd.concat([sd.iloc[1:], sd.iloc[:1].assign(sample_key="S7")], ignore_index=True)  # S1 gone, S7 new
    sd.to_parquet(new_dir / "sample_determinations.parquet", index=False)
    u = pd.read_parquet(os.path.join(prev, "universe_studies_all.parquet"))
    u.loc[1, "triage_verdict"] = "include"  # verdict flip on PRJ2
    u.to_parquet(new_dir / "universe_studies_all.parquet", index=False)
    out = str(tmp_path / "out2")
    bt.run(str(new_dir), out, RID, PV, PREV, previous_package=prev, release_date="2026-09-26")
    sd2 = pd.read_parquet(os.path.join(out, "sample_determinations.parquet"))
    assert sd2.loc[sd2["sample_key"] == "S7", "release_added"].iloc[0] == RID
    assert sd2.loc[sd2["sample_key"] == "S7", "package_added"].iloc[0] == PV
    allrows = pd.read_parquet(os.path.join(out, "sample_determinations_all.parquet"))
    gone = allrows[(allrows["sample_key"] == "S1") & allrows["release_retired"].notna()]
    assert len(gone) == 1 and gone.iloc[0]["release_retired"] == RID and gone.iloc[0]["retired_change_stage"] == "apply_findings"
    u2 = pd.read_parquet(os.path.join(out, "universe_studies_all.parquet"))
    assert u2["release_added"].tolist() == ["1.0.0", RID]


# ------------------------------------------------------------------------------------------------ real package
@pytest.fixture(scope="module")
def built(tmp_path_factory):
    if not _has_pkg():
        pytest.skip(f"no unpacked package at {PKG}")
    out = str(tmp_path_factory.mktemp("bt"))
    rid, pv, prev = _run_args()
    log = bt.run(PKG, out, rid, pv, prev, previous_package=PKG, release_date="2026-09-26")
    return out, log


def test_real_one_current_row_per_key_and_counts(built):
    out, log = built
    allrows = pd.read_parquet(os.path.join(out, "sample_determinations_all.parquet"))
    cur = allrows[allrows["release_retired"].isna()]
    assert len(cur) == 618_898 and not cur.duplicated(["sample_key", "field_name"]).any()
    assert cur["retired_reason"].isna().all() and cur["retired_change_stage"].isna().all()
    assert log["counts"]["n_samples"] == 154_206 and log["counts"]["n_studies_included"] == 389
    assert log["counts"]["n_determinations_current"] == 618_898 and log["counts"]["n_catalog_scope"] == 72_358


def test_real_retired_rows_rule(built):
    out, log = built
    allrows = pd.read_parquet(os.path.join(out, "sample_determinations_all.parquet"))
    ret = allrows[allrows["release_retired"].notna()]
    assert ret["release_retired"].notna().all() and ret["retired_change_stage"].notna().all() and ret["retired_reason"].notna().all()
    vh = pd.read_parquet(os.path.join(PKG, "value_history.parquet"))
    n_rule = int(vh["status"].isin(CFG["retired_statuses"]).sum())
    assert len(ret) == n_rule == 1_316, (len(ret), n_rule)
    # per-stage retirement packages follow the CHANGELOG-verified mapping
    got = {k: set(v) for k, v in ret.groupby("retired_change_stage")["release_retired"]}
    assert got == {"sample_unit_fix": {"1.1.0"}, "auditor_review:B2": {"1.2.0"}, "auditor_review:B9": {"1.2.0"},
                   "auditor_review:R3-3": {"1.2.1"}, "owner_decision": {"1.2.2"}}
    # sample_determinations_superseded is fully represented (223 = 75 sample_unit_fix + 148 B9 superseded)
    sup = pd.read_parquet(os.path.join(PKG, "sample_determinations_superseded.parquet"))
    assert len(sup) == 223
    assert int(ret["retired_change_stage"].isin(["sample_unit_fix"]).sum()) == 75


def test_real_release_ids_exist_in_registry_and_tables_unchanged(built):
    out, _ = built
    reg = pd.read_csv(os.path.join(out, "releases.csv"), dtype=str, keep_default_na=False)
    ids = set(reg["release_id"])
    assert reg["release_id"].tolist()[-1] == _run_args()[0]
    if _pkg_is_bitemporal():  # incremental mode: the previous release's registry row is carried verbatim
        assert "R2026.1" in ids and reg.set_index("release_id").loc["R2026.1", "package_version"] == "1.3.0"
    for spec in CFG["fact_tables"]:
        f = spec["file"]
        new = bt._read(os.path.join(out, f))
        old, _prior = bt.strip_prior(bt._read(os.path.join(PKG, f)))
        assert list(new.columns[-3:]) == list(bt.COLS), f
        assert new.drop(columns=list(bt.COLS)).equals(old), f"{f} content changed"
        if _prior is not None:  # nothing changed between 1.3.0 and this rebuild → release columns reproduced exactly
            assert (new[list(bt.COLS)].astype(str).fillna("").to_numpy() == _prior.astype(str).fillna("").to_numpy()).all(), f"{f} release columns not carried"
        assert set(new["release_added"].dropna()) <= ids, f
        assert new["release_retired"].isna().all() or (new["release_retired"].astype(str) == "").all(), f
    allrows = pd.read_parquet(os.path.join(out, "sample_determinations_all.parquet"))
    assert set(allrows["release_added"]) | set(allrows["release_retired"].dropna()) <= ids
    sd = pd.read_parquet(os.path.join(out, "sample_determinations.parquet"))
    vc = sd["release_added"].value_counts().to_dict()
    # historical ids are fixed; later releases (R2026.3 gap-fill rows, …) add their own keys when PKG_SRC is a newer package
    assert {k: vc.get(k) for k in ("1.0.0", "1.1.0", "1.2.0")} == {"1.0.0": 605_707, "1.1.0": 3_632, "1.2.0": 9_559}, vc
    assert (sd["package_added"] == sd["release_added"]).all()  # pre-1.3.0 ids ARE package versions

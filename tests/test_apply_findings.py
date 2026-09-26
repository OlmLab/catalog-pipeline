"""R1-06 / R1-09 / F2: apply_findings rebuilds the wide table, emits only when something applied, accepts `confirm`,
defaults route H for human evidence, and rejects actions outside audit/schema.json."""
import json
import os
import subprocess
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from catalog import apply_findings as AF  # noqa: E402
from catalog import findings_schema as FS  # noqa: E402

REQ = FS.finding_cols() + FS.struct_cols()


def _pkg(tmp_path):
    p = tmp_path / "pkg"
    p.mkdir()
    det = pd.DataFrame([
        dict(sample_key="SAMN1", field_name="delivery_mode", study_accession="PRJX1", field_value="vaginal", value_normalized="vaginal",
             confidence=0.7, evidence_source="sample.attr.delivery", evidence_locator="", evidence_quote="vaginal", evidence_limited_to_abstract=0.0,
             determined_by="r1", route="R1", scope="sample", parse_note="", group_audit=None, src_track="r1"),
        dict(sample_key="SAMN2", field_name="delivery_mode", study_accession="PRJX2", field_value="cesarean", value_normalized="cesarean",
             confidence=0.7, evidence_source="sample.attr.delivery", evidence_locator="", evidence_quote="c-section", evidence_limited_to_abstract=0.0,
             determined_by="r1", route="R1", scope="sample", parse_note="", group_audit=None, src_track="r1"),
    ])
    det.to_parquet(p / "sample_determinations.parquet", index=False)
    pd.DataFrame(columns=list(det.columns) + ["superseded_by", "superseded_reason"]).to_parquet(p / "sample_determinations_superseded.parquet", index=False)
    pd.DataFrame(dict(study_accession=["PRJX1", "PRJX2"], catalog_status=["included", "included"], note=["", ""])).to_parquet(p / "study_metadata_wide.parquet", index=False)
    pd.DataFrame(dict(study_accession=["PRJX1", "PRJX2"], catalog_status=["included", "included"], decision_stage=["x", "x"])).to_parquet(p / "universe_studies_all.parquet", index=False)
    pd.DataFrame(dict(sample_key=["SAMN1", "SAMN2"], study_accession=["PRJX1", "PRJX2"], delivery_mode=["vaginal", "cesarean"],
                      delivery_mode__confidence=[0.7, 0.7], delivery_mode__route=["R1", "R1"])).to_parquet(p / "sample_metadata_wide.parquet", index=False)
    return str(p)


def _findings(tmp_path, rows):
    d = tmp_path / "findings"
    d.mkdir(exist_ok=True)
    df = pd.DataFrame(rows)
    for c in REQ:
        if c not in df.columns:
            df[c] = ""
    df[REQ].to_csv(d / "2026-09-26_test.csv", index=False)
    return str(d)


def _run(pkg, fdir, out):
    p = subprocess.run([sys.executable, "-m", "catalog.apply_findings", "--package", pkg, "--findings", fdir, "--out", out],
                       capture_output=True, text=True, env={**os.environ, "PYTHONPATH": os.path.join(ROOT, "src")}, cwd=ROOT)
    assert p.returncode == 0, p.stdout + p.stderr
    return json.loads(p.stdout.strip().splitlines()[-1])


def test_noop_emits_no_tables(tmp_path):
    pkg = _pkg(tmp_path)
    fdir = _findings(tmp_path, [dict(date="2026-09-26", identifier="PRJX1", finding_type="documentation", current_state="x", proposed_change="y",
                                      evidence_quote="", evidence_source="", confidence="", action="note_only")])
    out = str(tmp_path / "out")
    r = _run(pkg, fdir, out)
    assert r["n_applied"] == 0
    assert not os.path.exists(os.path.join(out, "sample_determinations.parquet"))
    assert not os.path.exists(os.path.join(out, "APPLIED"))
    assert os.path.exists(os.path.join(out, "APPLY_FINDINGS_DIFF.md"))


def test_supersede_rewrites_wide_and_defaults_route_H(tmp_path):
    pkg = _pkg(tmp_path)
    fdir = _findings(tmp_path, [dict(date="2026-09-26", identifier="PRJX1", finding_type="value_error", current_state="vaginal", proposed_change="cesarean",
                                      evidence_quote="delivered by caesarean section", evidence_source="external_curation.human", confidence="0.9",
                                      action="supersede_determination", sample_key="SAMN1", field_name="delivery_mode", new_value="cesarean", source="issue#12")])
    out = str(tmp_path / "out")
    r = _run(pkg, fdir, out)
    assert r["n_applied"] == 1 and os.path.exists(os.path.join(out, "APPLIED"))
    det = pd.read_parquet(os.path.join(out, "sample_determinations.parquet"))
    wide = pd.read_parquet(os.path.join(out, "sample_metadata_wide.parquet"))
    row = det[(det.sample_key == "SAMN1") & (det.field_name == "delivery_mode")].iloc[0]
    assert row.value_normalized == "cesarean" and row.route == "H"
    w = wide[wide.sample_key == "SAMN1"].iloc[0]
    assert w.delivery_mode == "cesarean" and w.delivery_mode__route == "H" and float(w.delivery_mode__confidence) == 0.9
    # long/wide consistency for every auditor_review row
    for _, d in det[det.decision_stage == "auditor_review"].iterrows():
        assert wide.loc[wide.sample_key == d.sample_key, d.field_name].iloc[0] == d.value_normalized
    sup = pd.read_parquet(os.path.join(out, "sample_determinations_superseded.parquet"))
    assert len(sup) == 1 and sup.iloc[0].superseded_by == "auditor_review"


def test_confirm_writes_confirmations_and_verified_flag(tmp_path):
    pkg = _pkg(tmp_path)
    fdir = _findings(tmp_path, [dict(date="2026-09-26", identifier="SAMN2", finding_type="confirmed_correct", current_state="cesarean", proposed_change="confirmed",
                                      action="confirm", sample_key="SAMN2", field_name="delivery_mode", source="issue#13")])
    out = str(tmp_path / "out")
    r = _run(pkg, fdir, out)
    assert r["n_applied"] == 1
    conf = pd.read_parquet(os.path.join(out, "confirmations.parquet"))
    assert len(conf) == 1 and conf.iloc[0].confirmed_value == "cesarean"
    wide = pd.read_parquet(os.path.join(out, "sample_metadata_wide.parquet"))
    assert bool(wide.loc[wide.sample_key == "SAMN2", "delivery_mode__verified"].iloc[0]) is True
    assert bool(wide.loc[wide.sample_key == "SAMN1", "delivery_mode__verified"].iloc[0]) is False


def test_study_exclusion_propagates_to_universe_and_wide(tmp_path):
    pkg = _pkg(tmp_path)
    fdir = _findings(tmp_path, [dict(date="2026-09-26", identifier="PRJX2", finding_type="wrong_verdict", current_state="included", proposed_change="exclude",
                                      evidence_quote="all participants were adults", evidence_source="paper.fulltext.methods", confidence="0.9",
                                      action="study_verdict", new_value="excluded", reason_code="age_adult_only", source="issue#14")])
    out = str(tmp_path / "out")
    r = _run(pkg, fdir, out)
    assert r["n_applied"] == 1
    uni = pd.read_parquet(os.path.join(out, "universe_studies_all.parquet"))
    assert uni.loc[uni.study_accession == "PRJX2", "catalog_status"].iloc[0] == "excluded"
    wide = pd.read_parquet(os.path.join(out, "sample_metadata_wide.parquet"))
    assert "SAMN2" not in set(wide.sample_key)
    exc = pd.read_parquet(os.path.join(out, "sample_metadata_wide_excluded_by_review.parquet"))
    assert set(exc.sample_key) == {"SAMN2"}


def test_unknown_action_and_type_mismatch_rejected(tmp_path):
    pkg = _pkg(tmp_path)
    fdir = _findings(tmp_path, [
        dict(date="2026-09-26", identifier="PRJX1", finding_type="value_error", current_state="a", proposed_change="b", evidence_quote="q", evidence_source="external_curation.human", confidence="0.9", action="bogus"),
        dict(date="2026-09-26", identifier="PRJX1", finding_type="documentation", current_state="a", proposed_change="b", evidence_quote="q", evidence_source="external_curation.human", confidence="0.9", action="study_verdict", new_value="excluded", reason_code="age_adult_only"),
    ])
    out = str(tmp_path / "out")
    r = _run(pkg, fdir, out)
    assert r["n_applied"] == 0 and r["statuses"].get("rejected") == 2


def test_template_matches_schema():
    assert FS.render_template() == open(FS.TEMPLATE_PATH, encoding="utf-8").read()
    assert AF.ACTIONS == set(FS.load()["actions"]) and "confirm" in AF.ACTIONS

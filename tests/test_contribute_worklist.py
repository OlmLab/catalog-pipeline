"""R2026.2 contribute worklist (config/contribute.yaml, docs/CONTRIBUTE.md).

Two layers:
* config/parse tests that always run (schema shape, RESCUE_REPORT parser on a fixture, issue_url, priority formula);
* table tests that run against the built package when `build/package/contribute_worklist.csv` (or the unpacked source
  package with the artifact inputs) is present — skipped in CI without data (CATALOG_BOOTSTRAP_NO_DATA=1).
"""
import math
import os
import re
import sys
from urllib.parse import parse_qs, unquote, urlparse

import pandas as pd
import pytest
import yaml

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "src"))
from catalog.contribute import build_worklist as bw  # noqa: E402

CFG = yaml.safe_load(open(os.path.join(REPO, "config", "contribute.yaml"), encoding="utf-8"))
FIELDS = list(CFG["field_order"])
BLOCKERS = set(CFG["blocker_codes"])
CTYPES = set(CFG["contribution_types"])

PKG_OUT = os.path.join(REPO, "build", "package")
PKG_SRC = os.path.join(REPO, "data", "inputs", "data_package")
INPUTS = os.path.join(REPO, "data", "inputs", "contribute")


def _built_tables():
    """(worklist, fields, universe) from build/package if present, else built on the fly from PKG_SRC + INPUTS."""
    wl_p = os.path.join(PKG_OUT, CFG["tables"]["worklist"]["file"])
    if os.path.exists(wl_p) and os.path.exists(os.path.join(PKG_OUT, "universe_studies_all.parquet")):
        return (pd.read_csv(wl_p), pd.read_csv(os.path.join(PKG_OUT, CFG["tables"]["fields"]["file"])),
                pd.read_parquet(os.path.join(PKG_OUT, "universe_studies_all.parquet"), columns=["study_accession", "triage_verdict"]))
    if os.path.exists(os.path.join(PKG_SRC, "universe_studies_all.parquet")) and all(
            os.path.exists(os.path.join(INPUTS, f)) for f in bw.INPUT_FILES.values()):
        wl, fl, _ = bw.build(PKG_SRC, INPUTS, CFG, CFG["release_id"], CFG["package_version"])
        return wl, fl, pd.read_parquet(os.path.join(PKG_SRC, "universe_studies_all.parquet"), columns=["study_accession", "triage_verdict"])
    pytest.skip("no built package / inputs (CATALOG_BOOTSTRAP_NO_DATA)")


@pytest.fixture(scope="module")
def tables():
    return _built_tables()


# ---------------------------------------------------------------------------------------------------------------------
# config
def test_config_shape():
    assert CFG["release_id"] == "R2026.2" and CFG["package_version"] == "1.4.0"
    assert FIELDS == ["age", "delivery", "feeding", "preterm", "antibiotics", "probiotic"]
    assert {k: CFG["fields"][k]["weight"] for k in FIELDS} == {"age": 3.0, "delivery": 2.0, "feeding": 2.0, "preterm": 1.5, "antibiotics": 1.0, "probiotic": 0.5}
    assert set(CFG["blocker_order"]) | {"archive_only_uncertain", "complete"} == BLOCKERS
    assert CFG["blocker_order"][0] == "controlled_access" and CFG["blocker_order"][-1] == "partial_coverage"
    assert set(CFG["blocker_to_contribution_type"]) == BLOCKERS - {"complete"}
    assert set(CFG["blocker_to_contribution_type"].values()) <= CTYPES
    assert set(CFG["unlock_templates"]) == BLOCKERS - {"complete"}
    cols = CFG["tables"]["worklist"]["columns"]
    assert cols[:2] == ["rank", "study_accession"] and cols[-3:] == ["release_added", "release_retired", "package_added"]
    assert len(cols) == len(set(cols))
    assert CFG["tables"]["fields"]["columns"][-3:] == ["release_added", "release_retired", "package_added"]


def test_unlock_templates_fit_limit():
    lim = CFG["tables"]["worklist"]["text_limits"]["unlock_text"]
    for code, t in CFG["unlock_templates"].items():
        s = t.format(id_form="T1_S23", missing_fields=", ".join(FIELDS), accession="PRJNA000000")
        assert len(s) <= lim, (code, len(s))


def test_issue_url_roundtrip():
    u = bw.issue_url_for(CFG, "PRJNA123456", "id_key", "R2026.2")
    p = urlparse(u)
    assert p.scheme == "https" and p.netloc == "github.com" and p.path == "/OlmLab/infant-gut-catalog/issues/new"
    q = parse_qs(p.query)
    assert q["template"] == ["catalog-contribution.yml"] and q["labels"] == ["contribution"]
    assert q["study_accession"] == ["PRJNA123456"] and q["contribution_type"] == ["id_key"] and q["release_tag"] == ["R2026.2"]
    assert unquote(q["title"][0]) == "[contribution] PRJNA123456: id_key"


def test_priority_formula():
    cov = {"age": 0.0, "delivery": 0.25, "feeding": 1.0, "preterm": 0.0, "antibiotics": 0.0, "probiotic": 0.0}
    miss = ["age", "delivery", "preterm", "antibiotics", "probiotic"]
    s = bw.priority_score(CFG, cov, miss, 999)
    assert s == pytest.approx((3 + 2 * 0.75 + 1.5 + 1 + 0.5) * 3.0)
    assert bw.priority_score(CFG, cov, miss, 0) == 0.0
    assert bw.priority_score(CFG, cov, [], 999) == 0.0


RESCUE_FIXTURE = """## Per-study table

| study | n_samples | tables (cand / new accepted) | methods | fields gained (samples, new pairs) | status |
|---|---|---|---|---|---|
| PRJNA1 | 12 | 3 / 0 | – | – | no_match 2, below_gate 1 |
| PRJNA2 | 254 | 25 / 2 | orig | delivery_mode (56, 56 new) | rejected: unitless_age_header_unit_from_model 43; no_match 16 |

## Unprocessed / no-yield studies and their table ID forms

* PRJNA1 (12 samples): 3 candidate tables; sid_col forms ['Sample ID', 'BioSample', "Bifidobacterium longum subsp. infantis"]
* PRJNA3 (5 samples): no candidate table
"""


def test_parse_rescue_report_fixture():
    df = bw.parse_rescue_report(RESCUE_FIXTURE).set_index("study_accession")
    assert set(df.index) == {"PRJNA1", "PRJNA2", "PRJNA3"}
    assert df.loc["PRJNA1", "n_candidate_tables"] == 3 and df.loc["PRJNA1", "id_form"].startswith("Sample ID")
    assert df.loc["PRJNA2", "rescue_status"].startswith("rejected: unitless")
    assert df.loc["PRJNA3", "id_form"] == "no candidate table in supp_inventory"
    assert bw.pick_id_form(df.loc["PRJNA1", "id_form"], "x") == "Sample ID"
    assert bw.pick_id_form("BioSample, Run, Standard error", "x") == "Standard error"
    assert bw.pick_id_form(None, "x") == "x"


# ---------------------------------------------------------------------------------------------------------------------
# built tables
def test_open_studies_once_and_in_universe(tables):
    wl, fl, uni = tables
    assert wl["study_accession"].is_unique
    assert set(wl["study_accession"]) <= set(uni["study_accession"]), "accession outside universe_studies_all"
    v = uni.set_index("study_accession")["triage_verdict"]
    assert set(v.loc[wl["study_accession"]].unique()) <= {"include", "uncertain"}
    assert (wl["triage_verdict"].to_numpy() == v.loc[wl["study_accession"]].to_numpy()).all()
    assert list(wl["rank"]) == list(range(1, len(wl) + 1))
    assert list(wl.columns) == CFG["tables"]["worklist"]["columns"]
    assert list(fl.columns) == CFG["tables"]["fields"]["columns"]


def test_every_uncertain_is_open_and_flagged(tables):
    wl, _, uni = tables
    unc = set(uni.loc[uni["triage_verdict"] == "uncertain", "study_accession"])
    assert unc <= set(wl["study_accession"])
    assert (wl.loc[wl["study_accession"].isin(unc), "blocker_code"] == "archive_only_uncertain").all()
    assert (wl.loc[~wl["study_accession"].isin(unc), "blocker_code"] != "archive_only_uncertain").all()


def test_vocabularies(tables):
    wl, fl, _ = tables
    assert set(wl["blocker_code"]) <= BLOCKERS - {"complete"}
    assert set(fl["blocker_code"]) <= BLOCKERS
    assert set(wl["contribution_type"]) <= CTYPES
    assert (wl["contribution_type"] == wl["blocker_code"].map(CFG["blocker_to_contribution_type"])).all()
    assert set(wl[[f"best_tier_{k}" for k in FIELDS]].stack().unique()) <= {"R0", "R1", "R2", "R3", "R4"}
    assert set(fl["field"]) == set(FIELDS)


def test_coverages_and_missing(tables):
    wl, fl, _ = tables
    thr = CFG["missing_threshold"]
    for k in FIELDS:
        c = wl[f"coverage_{k}"]
        assert c.between(0, 1).all(), k
        miss = wl["missing_fields"].fillna("").str.split(";").apply(lambda xs: k in xs)
        assert ((c < thr) == miss).all(), k
    assert (wl["n_missing_fields"] == wl["missing_fields"].fillna("").str.split(";").apply(lambda xs: len([x for x in xs if x]))).all()
    assert (wl["n_missing_fields"] >= 1).all(), "a complete study is in the worklist"
    assert fl["coverage"].between(0, 1).all()
    assert (fl["n_with_value"] <= fl["n_catalog_scope"].where(fl["n_catalog_scope"] > 0, fl["n_with_value"])).all()


def test_priority_recomputes_from_row(tables):
    wl, _, _ = tables
    for _, r in wl.iterrows():
        miss = [x for x in str(r["missing_fields"]).split(";") if x and x != "nan"]
        exp = sum(CFG["fields"][k]["weight"] * (1 - r[f"coverage_{k}"]) for k in miss) * math.log10(r["n_catalog_scope"] + 1)
        assert r["priority_score"] == pytest.approx(exp, abs=1e-5), r["study_accession"]
    assert (wl["priority_score"].diff().dropna() <= 1e-9).all(), "rank not monotone in priority_score"


def test_issue_urls_parse(tables):
    wl, _, _ = tables
    for _, r in wl.iterrows():
        q = parse_qs(urlparse(r["issue_url"]).query)
        assert q["study_accession"] == [r["study_accession"]] and q["contribution_type"] == [r["contribution_type"]]
        assert r["study_accession"] in unquote(q["title"][0]) and q["release_tag"] == [r["release_added"]]


def test_text_limits_and_release_columns(tables):
    wl, fl, _ = tables
    assert wl["blocker_detail"].str.len().max() <= CFG["tables"]["worklist"]["text_limits"]["blocker_detail"]
    assert wl["unlock_text"].str.len().max() <= CFG["tables"]["worklist"]["text_limits"]["unlock_text"]
    assert fl["evidence"].str.len().max() <= CFG["tables"]["fields"]["text_limits"]["evidence"]
    for df in (wl, fl):
        assert (df["release_added"] == CFG["release_id"]).all() and df["release_retired"].isna().all()
        assert (df["package_added"].astype(str) == CFG["package_version"]).all()
    assert wl["blocker_detail"].notna().all() and wl["unlock_text"].notna().all()


def test_fields_table_six_rows_per_study(tables):
    wl, fl, _ = tables
    n = fl.groupby("study_accession").size()
    assert set(n.index) == set(wl["study_accession"]) and (n == 6).all()
    assert not fl.duplicated(["study_accession", "field"]).any()
    m = fl.merge(wl[["study_accession", "missing_fields"]], on="study_accession")
    is_missing = m.apply(lambda r: r["field"] in str(r["missing_fields"]).split(";"), axis=1)
    assert ((m["blocker_code"] == "complete") == ~is_missing).all()


def test_no_email_addresses(tables):
    wl, fl, _ = tables
    for df in (wl, fl):
        txt = " ".join(df.fillna("").astype(str).to_numpy().ravel().tolist())
        assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", txt), "e-mail-like token in the worklist"

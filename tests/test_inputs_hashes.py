"""A4: config/inputs.json lists every producing script and data input with artifact version_id + sha256.

* Every `code` entry must exist at its repo_path; for entries copied verbatim the sha256 of the repo file equals
  the recorded artifact sha256; for entries the skeleton rewrote (import shim, model resolver, prompt path),
  `sha256_repo` records the post-rewrite hash and must match the file on disk.
* Data inputs are checked only when present under data/inputs/ (bootstrap.py materialises them); otherwise skipped.
"""
import hashlib
import json
import os

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUTS = json.load(open(os.path.join(REPO, "config", "inputs.json")))


def _sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


DATA_GROUPS = [g for g in INPUTS["inputs"] if g != "code"]  # data, sandpiper, authors, reports (R1-03/R1-08)


def test_inputs_json_shape():
    assert "inputs" in INPUTS and "code" in INPUTS["inputs"] and "data" in INPUTS["inputs"]
    assert {"sandpiper", "authors", "reports"} <= set(INPUTS["inputs"]), "R1-03/R1-08 groups missing"
    for grp, entries in INPUTS["inputs"].items():
        for e in entries:
            assert e["filename"] and e["artifact_id"], e
            if str(e["artifact_id"]).startswith("skill:"):
                # vendored skill files have no artifact version (R1-18): version_id may be null and is skipped by bootstrap
                assert e["version_id"] in (None, "") or len(e["version_id"]) == 36, e
                continue
            assert e["version_id"] and len(e["version_id"]) == 36, f"version_id must be a full UUID: {e}"
            if grp != "code":
                assert e.get("sha256") or e.get("note"), f"data input without sha256 needs a note: {e['filename']}"


def test_current_package_is_required_and_v1_is_not():
    data = {e["filename"]: e for e in INPUTS["inputs"]["data"]}
    assert data["data_package_v1.2.1.zip"]["required"] is True
    assert data["data_package_v1.zip"]["required"] is False


@pytest.mark.parametrize("entry", INPUTS["inputs"]["code"], ids=lambda e: e["filename"])
def test_code_copy_hash(entry):
    p = os.path.join(REPO, entry["repo_path"])
    assert os.path.exists(p), f"missing {entry['repo_path']}"
    expected = entry.get("sha256_repo") or entry["sha256"]
    assert _sha(p) == expected, f"{entry['repo_path']} changed since inputs.json was written (re-run `make inputs-json`)"


_DATA_ENTRIES = [(g, e) for g in DATA_GROUPS for e in INPUTS["inputs"][g] if not str(e["artifact_id"]).startswith("skill:")]


@pytest.mark.parametrize("grp,entry", _DATA_ENTRIES, ids=lambda x: x if isinstance(x, str) else x["filename"])
def test_data_input_hash(grp, entry):
    sub = entry.get("dest_subdir") or ("" if grp == "data" else grp)
    p = os.path.join(REPO, "data", "inputs", sub, entry["filename"]) if sub else os.path.join(REPO, "data", "inputs", entry["filename"])
    if not os.path.exists(p):
        pytest.skip("not materialised (run bootstrap.py)")
    if not entry.get("sha256"):
        pytest.skip("no hash recorded (working_data artifact)")
    assert _sha(p) == entry["sha256"]

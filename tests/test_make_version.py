"""R1-11: deterministic zip (byte-identical across builds), zip sha256 sidecar, --check fails on unlisted tables."""
import hashlib
import json
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from catalog import make_version as mv  # noqa: E402


def _pkg(tmp_path, ver="9.9.9"):
    d = tmp_path / "pkg"
    d.mkdir()
    pd.DataFrame({"a": [1, 2, 3]}).to_parquet(d / "t.parquet", index=False)
    (d / "README.md").write_text(f"# data package v{ver} (2026-09-26)\n")
    return str(d)


def test_zip_is_byte_identical_and_sidecar_matches(tmp_path):
    d = _pkg(tmp_path)
    v = mv.build(d, "9.9.9", "2026-09-26")
    json.dump(v, open(os.path.join(d, "VERSION.json"), "w"), indent=1, sort_keys=True)
    z1 = str(tmp_path / "b1" / "p.zip")
    z2 = str(tmp_path / "b2" / "p.zip")
    i1 = mv.build_zip(d, z1, "2026-09-26")
    import time
    time.sleep(1.1)  # a different wall-clock second must not change the bytes
    os.utime(os.path.join(d, "t.parquet"))  # and neither must a different mtime
    i2 = mv.build_zip(d, z2, "2026-09-26")
    assert i1["sha256"] == i2["sha256"] == hashlib.sha256(open(z1, "rb").read()).hexdigest()
    side = mv.write_sidecar(d, z1, i1)
    assert json.load(open(side))["package_zip"]["sha256"] == i1["sha256"]
    assert open(z1 + ".sha256").read().split()[0] == i1["sha256"]
    assert mv.check(d, "9.9.9", z1) == []


def test_check_fails_on_unlisted_table(tmp_path):
    d = _pkg(tmp_path)
    v = mv.build(d, "9.9.9", "2026-09-26")
    json.dump(v, open(os.path.join(d, "VERSION.json"), "w"))
    assert mv.check(d, "9.9.9") == []
    json.dump({"x": 1}, open(os.path.join(d, "build_counts.json"), "w"))  # added AFTER the manifest
    probs = mv.check(d, "9.9.9")
    assert any("build_counts.json" in p and "not listed" in p for p in probs), probs


def test_check_fails_on_readme_version_mismatch(tmp_path):
    d = _pkg(tmp_path, ver="1.2.0")
    v = mv.build(d, "1.2.1", "2026-09-26")
    json.dump(v, open(os.path.join(d, "VERSION.json"), "w"))
    assert any("README.md says v1.2.0" in p for p in mv.check(d, "1.2.1"))

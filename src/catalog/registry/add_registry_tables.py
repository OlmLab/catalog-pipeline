"""Copy harvested registry side tables (papers / authors / BioProject records, …) into the package with the release columns.
Usage: python -m catalog.registry.add_registry_tables --package build/package --release-id R2026.5 --package-version 1.7.0 <parquet> [<parquet> …]
Rows keep an existing release_added (a re-shipped table); missing release columns are appended (release_retired = null).
The column list of each table must match audit/registry_schema.json (minus the release columns) — a drift fails loudly."""
from __future__ import annotations

import argparse
import json
import os
import sys

import pandas as pd

RELEASE_COLS = ("release_added", "release_retired", "package_added")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", required=True), ap.add_argument("--release-id", required=True), ap.add_argument("--package-version", required=True)
    ap.add_argument("--schema", default=os.path.join(os.path.dirname(__file__), "..", "..", "..", "audit", "registry_schema.json"))
    ap.add_argument("--previous-dir", help="previous package dir: same-named tables there provide release_added / retirements")
    ap.add_argument("tables", nargs="+")
    a = ap.parse_args(argv)
    schema = json.load(open(a.schema))["tables"]
    out = {}
    for t in a.tables:
        name = os.path.basename(t)
        df = pd.read_parquet(t)
        if name in schema:
            want = [c["name"] for c in schema[name]["columns"] if c["name"] not in RELEASE_COLS]
            have = [c for c in df.columns if c not in RELEASE_COLS]
            assert have == want, f"{name}: columns differ from audit/registry_schema.json: {sorted(set(have) ^ set(want))}"
        if "release_added" not in df.columns:
            df["release_added"] = a.release_id
        if "release_retired" not in df.columns:
            df["release_retired"] = None
        if "package_added" not in df.columns:
            df["package_added"] = a.package_version
        prev_p = os.path.join(a.previous_dir, name) if a.previous_dir else None
        if prev_p and os.path.exists(prev_p):
            from catalog.registry.build_registry import carry_release_columns
            df = carry_release_columns(df, pd.read_parquet(prev_p), schema[name]["key"] if name in schema else [df.columns[0]], a.release_id)
        df.to_parquet(os.path.join(a.package, name), index=False)
        out[name] = len(df)
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python
"""plot_field_coverage.py — regenerate static/field_coverage.png from field_coverage_summary.csv (R1-08).

Deterministic (Agg backend, fixed figure size, metadata stripped). The CSV is the package table; columns are detected:
the field column is the first non-numeric column, the plotted value is `coverage_catalog_scope` when present, else the
first column whose name starts with `coverage` (values in [0, 1] are shown as %; values > 1 are taken as %).

    python scripts/plot_field_coverage.py --summary build/package/field_coverage_summary.csv --out data/inputs/reports/field_coverage.png
"""
from __future__ import annotations

import argparse

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--summary", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--value-col", default=None)
    a = ap.parse_args(argv)
    df = pd.read_csv(a.summary)
    field_col = next(c for c in df.columns if not pd.api.types.is_numeric_dtype(df[c]))
    val = a.value_col or ("coverage_catalog_scope" if "coverage_catalog_scope" in df.columns
                          else next(c for c in df.columns if c.startswith("coverage") and pd.api.types.is_numeric_dtype(df[c])))
    d = df[[field_col, val]].dropna().sort_values(val, ascending=True)
    y = d[val].astype(float)
    if y.max() <= 1.0:
        y = y * 100
    fig, ax = plt.subplots(figsize=(8, 0.35 * len(d) + 1.2))
    ax.barh(d[field_col], y, color="#3b6ea5")
    for i, v in enumerate(y):
        ax.text(min(v + 1, 99), i, f"{v:.0f} %", va="center", fontsize=8)
    ax.set_xlim(0, 100)
    ax.set_xlabel(f"{val.replace('_', ' ')} (% of samples with a committed value)")
    ax.set_title("Per-field metadata coverage")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(a.out, dpi=120, metadata={"Software": None, "Creation Time": None})
    print(a.out, len(d), val)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

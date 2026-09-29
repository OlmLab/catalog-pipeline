"""Merge the R3 (full-text cohort statement) leaf shards for the gut_all scope into the pipeline inputs.

Leaves emit one study_all determination per (study, field) after two-replicate agreement and quote verification; a few
studies carry two agreed health_condition codes (a disease code next to `intervention_cohort`, or two cardiometabolic codes).
Rule applied here (recorded in parse_note): keep the disease code over `intervention_cohort`; otherwise keep the higher
confidence, then the first-listed code; the alternative code/detail is appended to parse_note as `alt=<code>`.
Also builds the side tables (unreplicated, subgroups, study summary) as single files for the package docs / future R3 work.

usage: python -m catalog.scopes.merge_r3_shards --in-dir data/inputs/gut/r3/shards --out-dir data/inputs/gut/r3 [--prefix gut_r3]
(--prefix gut_r3b merges the R3b new-field shards — lifestyle / location_* / collection_date — into gut_r3b_*; --prefix gut_r4b the R4b shards.)
"""
import argparse
import glob
import json
import os

import pandas as pd

KINDS = ("determinations", "unreplicated", "subgroups", "study_summary")


def load_kind(in_dir: str, kind: str, prefix: str = "gut_r3") -> pd.DataFrame:
    fs = sorted(glob.glob(os.path.join(in_dir, f"{prefix}_{kind}_*shard_*.parquet")))
    if not fs:
        return pd.DataFrame()
    parts = []
    for f in fs:
        d = pd.read_parquet(f)
        d["r3_shard"] = os.path.basename(f).split(prefix + "_" + kind + "_")[1].replace(".parquet", "")
        parts.append(d)
    return pd.concat(parts, ignore_index=True)


def resolve_duplicates(det: pd.DataFrame) -> pd.DataFrame:
    """One row per (study, field); the detail row follows its health_condition row's choice."""
    det = det.copy()
    det["_rank"] = (det.value_normalized == "intervention_cohort").astype(int)  # disease codes first
    det["_order"] = range(len(det))
    hc = det[det.field_name == "health_condition"].sort_values(["study_accession", "_rank", "confidence", "_order"], ascending=[True, True, False, True])
    keep_hc = hc.drop_duplicates("study_accession")
    dropped_hc = hc[~hc.index.isin(keep_hc.index)]
    alt = dropped_hc.groupby("study_accession").value_normalized.apply(lambda s: "alt=" + "|".join(s)).to_dict()
    # detail rows: keep the one whose shard/order pairs with the kept code (same shard, nearest following row)
    det_rows = det[det.field_name == "health_condition_detail"]
    keep_detail_idx = []
    for st, g in det_rows.groupby("study_accession"):
        if len(g) == 1:
            keep_detail_idx.append(g.index[0])
            continue
        kept = keep_hc[keep_hc.study_accession == st]
        if len(kept):
            o = kept._order.iloc[0]
            after = g[g._order > o].sort_values("_order")
            keep_detail_idx.append(after.index[0] if len(after) else g.sort_values("_order").index[0])
        else:
            keep_detail_idx.append(g.sort_values("confidence", ascending=False).index[0])
    others = det[~det.field_name.isin(["health_condition", "health_condition_detail"])].sort_values(["confidence", "_order"], ascending=[False, True]).drop_duplicates(["study_accession", "field_name"])
    out = pd.concat([keep_hc, det.loc[keep_detail_idx], others]).sort_values("_order")
    note_add = out.study_accession.map(alt).astype(object)
    has = note_add.notna() & (out.field_name == "health_condition")
    if has.any():
        out.loc[has, "parse_note"] = out.loc[has, "parse_note"].fillna("").astype(str).str.rstrip("; ").where(lambda s: s == "", lambda s: s + "; ") + note_add[has].astype(str)
    return out.drop(columns=["_rank", "_order"]), len(det) - len(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-dir", required=True), ap.add_argument("--out-dir", required=True), ap.add_argument("--prefix", default="gut_r3")
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    det = load_kind(a.in_dir, "determinations", a.prefix)
    if not len(det):
        raise SystemExit(f"no {a.prefix}_determinations_*shard_*.parquet in {a.in_dir}")
    det, n_dropped = resolve_duplicates(det)
    det.drop(columns=["r3_shard"]).to_parquet(os.path.join(a.out_dir, f"{a.prefix}_determinations_merged.parquet"), index=False)
    summary = {"n_determinations": int(len(det)), "n_studies": int(det.study_accession.nunique()), "n_duplicates_resolved": int(n_dropped),
               "per_field": det.field_name.value_counts().to_dict(), "n_shards": int(det.r3_shard.nunique())}
    for kind in KINDS[1:]:
        d = load_kind(a.in_dir, kind, a.prefix)
        if len(d):
            for c in d.columns:  # leaves differ in side-table typing; strings are the common denominator
                if d[c].dtype == object or str(d[c].dtype) in ("bool", "boolean"):
                    d[c] = d[c].map(lambda v: None if v is None or (isinstance(v, float) and pd.isna(v)) else str(v))
            d.to_parquet(os.path.join(a.out_dir, f"{a.prefix}_{kind}_all.parquet"), index=False)
            summary[f"n_{kind}"] = int(len(d))
    json.dump(summary, open(os.path.join(a.out_dir, f"{a.prefix}_merge_summary.json"), "w"), indent=1)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()

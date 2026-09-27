"""apply_gapfill.py — append a gapfill_samples.py output directory to an unpacked package (RUNBOOK §3 'new samples in an
included study'). Deterministic; never modifies an existing row (asserted).

  python -m catalog.release.apply_gapfill --package build/package --gapfill build/gapfill_R2026.2 [--out build/package_gapfilled]

Appends: runs_new -> runs.parquet; samples_new_wide -> sample_metadata_wide.parquet (+ .csv.gz when present);
sample_determinations_new -> sample_determinations.parquet AND sample_determinations_all.parquet; sample_subjects_new ->
sample_subjects.parquet; sandpiper_run_qc_new -> sandpiper_run_qc.parquet; sandpiper_sample_summary_new ->
sandpiper_sample_summary.parquet. Updates study_metadata_wide (n_samples, n_runs, n_biosamples, n_sample_rows, scope counts,
cov_*, sp_* coverage) and universe_studies_all (n_samples, n_runs) for the study from study_metadata_wide_delta.json, and
build_counts.json totals. Writes APPLY_GAPFILL_<study>.json with before/after counts and the no-change proof (row hashes).
"""
import argparse, hashlib, json, os, shutil
import pandas as pd

TABLES = [("runs_new.parquet", "runs.parquet", "run_accession"),
          ("samples_new_wide.parquet", "sample_metadata_wide.parquet", "sample_key"),
          ("sample_determinations_new.parquet", "sample_determinations.parquet", None),
          ("sample_determinations_new.parquet", "sample_determinations_all.parquet", None),
          ("sample_subjects_new.parquet", "sample_subjects.parquet", "sample_key"),
          ("sandpiper_run_qc_new.parquet", "sandpiper_run_qc.parquet", "run_accession"),
          ("sandpiper_sample_summary_new.parquet", "sandpiper_sample_summary.parquet", "sample_key")]
STUDY_DELTA_KEYS = ["n_samples", "n_runs", "n_biosamples", "n_sample_rows", "n_infant_scope_samples", "n_body_site_excluded", "n_catalog_scope",
                    "n_age_scope_infant", "n_adult_flagged", "n_non_infant_role", "n_infant_evidenced", "n_study_all_infant", "n_age_unknown_mixed_study",
                    "n_age_unknown_no_study_estimate", "n_mothers", "n_infant_role_samples", "sp_n_samples_profiled", "sp_frac_samples_profiled",
                    "sp_n_runs_profiled", "sp_frac_runs_profiled"]


def _row_hash(df):
    """Order-independent multiset hash of all rows (string form)."""
    s = pd.util.hash_pandas_object(df.astype(str), index=False)
    return hashlib.sha256(pd.Series(sorted(s.values)).values.tobytes()).hexdigest()


def _align(new, old, name):
    missing = [c for c in old.columns if c not in new.columns]
    extra = [c for c in new.columns if c not in old.columns]
    if extra:
        raise SystemExit(f"{name}: gapfill table has columns not in the package: {extra}")
    for c in missing:
        new[c] = None
    new = new[list(old.columns)]
    for c in old.columns:
        if str(old[c].dtype) != str(new[c].dtype):
            try:
                new[c] = new[c].astype(old[c].dtype)
            except (TypeError, ValueError):
                pass
    return new


def apply(package, gapfill, out=None):
    out = out or package
    if os.path.abspath(out) != os.path.abspath(package):
        if os.path.exists(out):
            shutil.rmtree(out)
        shutil.copytree(package, out)
    delta = json.load(open(os.path.join(gapfill, "study_metadata_wide_delta.json")))
    study = delta["study_accession"]
    report = dict(study=study, tables={}, study_metadata_wide={}, universe_studies_all={}, build_counts={})
    for src, dst, key in TABLES:
        sp, dp = os.path.join(gapfill, src), os.path.join(out, dst)
        if not os.path.exists(sp) or not os.path.exists(dp):
            report["tables"][dst] = "skipped (missing)"; continue
        new, old = pd.read_parquet(sp), pd.read_parquet(dp)
        if new.empty:
            report["tables"][dst] = dict(before=len(old), added=0, after=len(old)); continue
        new = _align(new, old, dst)
        if key:
            dup = set(new[key]) & set(old[key])
            assert not dup, f"{dst}: {len(dup)} {key} values already present"
        before_hash = _row_hash(old)
        merged = pd.concat([old, new], ignore_index=True)
        assert _row_hash(merged.iloc[:len(old)]) == before_hash, f"{dst}: existing rows changed"
        assert len(merged) == len(old) + len(new)
        merged.to_parquet(dp, index=False)
        if dst == "sample_metadata_wide.parquet" and os.path.exists(os.path.join(out, "sample_metadata_wide.csv.gz")):
            merged.to_csv(os.path.join(out, "sample_metadata_wide.csv.gz"), index=False, compression="gzip")
        report["tables"][dst] = dict(before=int(len(old)), added=int(len(new)), after=int(len(merged)), existing_rows_hash=before_hash[:16])
    # study_metadata_wide (+ csv twin)
    for fn in ("study_metadata_wide.parquet", "study_metadata_wide.csv"):
        p = os.path.join(out, fn)
        if not os.path.exists(p):
            continue
        sm = pd.read_parquet(p) if fn.endswith(".parquet") else pd.read_csv(p)
        i = sm.index[sm.study_accession == study]
        assert len(i) == 1, f"{fn}: study row not unique"
        others_before = _row_hash(sm.drop(index=i))
        for k in STUDY_DELTA_KEYS + [c for c in delta if c.startswith("cov_")]:
            if k in sm.columns and k in delta:
                report["study_metadata_wide"][k] = dict(before=(None if pd.isna(sm.loc[i[0], k]) else (sm.loc[i[0], k].item() if hasattr(sm.loc[i[0], k], "item") else sm.loc[i[0], k])), after=delta[k])
                sm.loc[i, k] = delta[k]
        assert _row_hash(sm.drop(index=i)) == others_before, f"{fn}: other studies changed"
        (sm.to_parquet(p, index=False) if fn.endswith(".parquet") else sm.to_csv(p, index=False))
    # universe_studies_all
    p = os.path.join(out, "universe_studies_all.parquet")
    if os.path.exists(p):
        ua = pd.read_parquet(p); i = ua.index[ua.study_accession == study]
        others_before = _row_hash(ua.drop(index=i))
        for k in ("n_samples", "n_runs"):
            if k in ua.columns:
                report["universe_studies_all"][k] = dict(before=ua.loc[i, k].tolist(), after=delta[k]); ua.loc[i, k] = delta[k]
        assert _row_hash(ua.drop(index=i)) == others_before
        ua.to_parquet(p, index=False)
    # build_counts
    # Sandpiper study-level tables (F13: build_site asserts n_samples_study == wide-table rows per study)
    n_new = report["tables"].get("sample_metadata_wide.parquet", {}).get("added", 0)
    n_new_runs = report["tables"].get("runs.parquet", {}).get("added", 0)
    n_new_profiled = report["tables"].get("sandpiper_sample_summary.parquet", {}).get("added", 0)
    for fn in ("sandpiper_study_panel_status.csv", "sandpiper_study_coverage.csv", "sandpiper_study_qc_flags.csv"):
        pth = os.path.join(out, fn)
        if not os.path.exists(pth):
            continue
        t = pd.read_csv(pth)
        m = t.study_accession == study
        if not m.any():
            continue
        for c, add in (("n_samples_study", n_new), ("n_samples", n_new), ("n_runs", n_new_runs), ("n_infant_scope_samples", 0),
                       ("n_profiled", n_new_profiled), ("n_samples_profiled", n_new_profiled), ("n_runs_profiled", n_new_profiled)):
            if c in t.columns and add:
                t.loc[m, c] = t.loc[m, c].astype(int) + int(add)
        if "miss_published_after_snapshot_horizon" in t.columns and n_new_runs and not n_new_profiled:
            t.loc[m, "miss_published_after_snapshot_horizon"] = t.loc[m, "miss_published_after_snapshot_horizon"].astype(int) + int(n_new_runs)
        for num, den, col in (("n_runs_profiled", "n_runs", "frac_runs_profiled"), ("n_samples_profiled", "n_samples", "frac_samples_profiled"), ("n_profiled", "n_samples_study", "frac_samples_profiled")):
            if col in t.columns and num in t.columns and den in t.columns:
                t.loc[m, col] = (t.loc[m, num].astype(float) / t.loc[m, den].replace(0, pd.NA).astype(float)).round(3)
        t.to_csv(pth, index=False)
        report["tables"][fn] = {"updated_rows": int(m.sum())}
    p = os.path.join(out, "build_counts.json")
    if os.path.exists(p):
        bc = json.load(open(p))
        add = {"n_samples": report["tables"].get("sample_metadata_wide.parquet", {}).get("added", 0), "n_runs": report["tables"].get("runs.parquet", {}).get("added", 0),
               "n_biosample_units": report["tables"].get("sample_metadata_wide.parquet", {}).get("added", 0),
               "n_determinations_current": report["tables"].get("sample_determinations.parquet", {}).get("added", 0),
               "n_determinations_all": report["tables"].get("sample_determinations_all.parquet", {}).get("added", 0),
               "n_body_site_excluded": delta.get("n_body_site_excluded", 0) - (delta.get("before", {}).get("n_body_site_excluded") or 0),
               "n_profiled_samples": report["tables"].get("sandpiper_sample_summary.parquet", {}).get("added", 0)}
        for k, v in add.items():
            if k in bc and isinstance(v, int):
                report["build_counts"][k] = dict(before=bc[k], after=bc[k] + v); bc[k] = bc[k] + v
        bc.setdefault("gapfill", []).append(dict(study=study, n_samples_added=add["n_samples"], n_runs_added=add["n_runs"], source="gapfill_samples"))
        json.dump(bc, open(p, "w"), indent=1, sort_keys=True)
    json.dump(report, open(os.path.join(out, f"APPLY_GAPFILL_{study}.json"), "w"), indent=1, default=str)
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--package", required=True); ap.add_argument("--gapfill", required=True); ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    rep = apply(a.package, a.gapfill, a.out)
    print(json.dumps({k: v for k, v in rep.items() if k == "tables"}, indent=1))


if __name__ == "__main__":
    main()

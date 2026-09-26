#!/usr/bin/env python
"""bitemporal.py — append the release columns to every fact table of a data package and build the history table.

Spec: config/releases.yaml + docs/RELEASES.md (MATURITY_PLAN §2). Deterministic; no LLM; never alters an existing
value or the row order of a table — it only APPENDS columns (release_added, release_retired, package_added) and
writes two new files: sample_determinations_all.parquet (current ∪ retired determinations) and releases.csv.

    python -m catalog.release.bitemporal --package build/package --out build/package \
        --release-id R2026.1 --package-version 1.3.0 --previous-package-version 1.2.2 \
        [--previous-package data/inputs/data_package] [--release-date 2026-09-26]

Seeding of release_added for rows that already existed before the first numbered release is RECONSTRUCTED
(docs/RELEASES.md §3 "Provenance"): newest value_history.change_stage touching the (sample_key, field_name) →
package (config change_stage_to_package), sample_determinations.src_track → package (src_track_to_package), else the
table's default_release_added. With --previous-package, rows absent from the previous package get
release_added = --release-id and rows of the previous package that disappeared become retired rows.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys

import pandas as pd
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
CONFIG_DIR = os.environ.get("CATALOG_CONFIG_DIR", os.path.join(REPO, "config"))
COLS = ("release_added", "release_retired", "package_added")
ALL_EXTRA = COLS + ("retired_reason", "retired_change_stage")
CSV_READ = dict(dtype=str, keep_default_na=False, na_filter=False)
COUNT_KEYS = ("n_studies_included", "n_samples", "n_catalog_scope", "n_determinations_current", "sandpiper_version")


def load_config(path: str | None = None) -> dict:
    return yaml.safe_load(open(path or os.path.join(CONFIG_DIR, "releases.yaml"), encoding="utf-8"))


def release_order(cfg: dict) -> list[str]:
    """All release ids oldest → newest (historical package semvers, then numbered releases)."""
    return [h["id"] for h in cfg["history"]] + [r["release_id"] for r in cfg["releases"]]


def package_of(cfg: dict, release_id: str) -> str:
    for h in cfg["history"]:
        if h["id"] == release_id:
            return h["package_version"]
    for r in cfg["releases"]:
        if r["release_id"] == release_id:
            return r["package_version"]
    raise KeyError(release_id)


def _read(path: str) -> pd.DataFrame:
    if path.endswith(".parquet"):
        return pd.read_parquet(path)
    return pd.read_csv(path, **CSV_READ)


def _write(df: pd.DataFrame, path: str) -> None:
    if path.endswith(".parquet"):
        df.to_parquet(path, index=False)
    else:
        df.to_csv(path, index=False)


def _key_index(df: pd.DataFrame, key: list[str]) -> pd.Index:
    if len(key) == 1:
        return pd.Index(df[key[0]].astype(str))
    return pd.MultiIndex.from_frame(df[key].astype(str))


def append_cols(df: pd.DataFrame, release_added: pd.Series, cfg: dict, release_id: str, package_version: str) -> pd.DataFrame:
    """Append the three release columns; every row is current (release_retired null)."""
    for c in COLS:
        assert c not in df.columns, f"{c} already present"
    out = df.copy()
    ra = pd.Series(release_added, index=df.index).astype("string")
    out["release_added"] = ra
    out["release_retired"] = pd.Series([pd.NA] * len(df), index=df.index, dtype="string")
    out["package_added"] = ra.map(lambda r: package_version if r == release_id else package_of(cfg, r)).astype("string")
    return out


# ----------------------------------------------------------------------------------------------- determinations
def seed_determinations(sd: pd.DataFrame, vh: pd.DataFrame, cfg: dict, rank: dict, default: str,
                        prev_sd: pd.DataFrame | None, release_id: str) -> tuple[pd.Series, dict]:
    stage_pkg = cfg["change_stage_to_package"]
    track_pkg = cfg["src_track_to_package"]
    unknown = sorted(set(vh["change_stage"].dropna()) - set(stage_pkg))
    assert not unknown, f"value_history.change_stage without a package mapping in config/releases.yaml: {unknown}"
    key = ["sample_key", "field_name"]
    v = vh[key + ["change_stage"]].copy()
    v["pkg"] = v["change_stage"].map(stage_pkg)
    v["r"] = v["pkg"].map(rank)
    newest = v.sort_values("r", kind="stable").drop_duplicates(key, keep="last").set_index(key)["pkg"]
    idx = pd.MultiIndex.from_frame(sd[key].astype(str))
    from_hist = pd.Series(newest.reindex(idx).to_numpy(), index=sd.index, dtype=object)
    from_track = (sd["src_track"].map(track_pkg).astype(object) if "src_track" in sd.columns
                  else pd.Series([None] * len(sd), index=sd.index, dtype=object))
    ra = pd.Series([default] * len(sd), index=sd.index, dtype=object)
    for cand in (from_hist, from_track):
        m = cand.notna()
        cr = cand.where(m).map(lambda p: rank.get(p, -1) if isinstance(p, str) else -1)
        take = m & (cr > ra.map(rank))
        ra[take] = cand[take]
    n_new = 0
    if prev_sd is not None:
        prev_idx = pd.MultiIndex.from_frame(prev_sd[key].astype(str))
        is_new = ~idx.isin(prev_idx)
        ra[is_new] = release_id
        n_new = int(is_new.sum())
    prov = {"from_value_history": int(from_hist.notna().sum()), "from_src_track": int(from_track.notna().sum()),
            "new_in_release": n_new, "default": int((ra == default).sum())}
    return ra, prov


def retired_rows(sd_cols: list[str], vh: pd.DataFrame, cfg: dict, superseded: pd.DataFrame | None,
                 default_added: str) -> pd.DataFrame:
    """Retired published values reconstructed from value_history (rule: status ∈ retired_statuses)."""
    stage_pkg = cfg["change_stage_to_package"]
    ret_st, never = set(cfg["retired_statuses"]), set(cfg["never_published_statuses"])
    other = sorted(set(vh["status"].dropna()) - ret_st - never)
    assert not other, f"value_history.status not classified in config/releases.yaml: {other}"
    r = vh[vh["status"].isin(ret_st)].reset_index(drop=True)
    out = pd.DataFrame({c: (r[c].to_numpy() if c in r.columns else [None] * len(r)) for c in sd_cols})
    out["release_added"] = default_added
    out["release_retired"] = r["change_stage"].map(stage_pkg).to_numpy()
    out["package_added"] = default_added
    out["retired_reason"] = r["reason"].to_numpy()
    out["retired_change_stage"] = r["change_stage"].to_numpy()
    assert out["release_retired"].notna().all()
    if superseded is not None:  # cross-check: every superseded row is among the retired rows (same key + value)
        k = ["sample_key", "field_name", "value_normalized"]
        a = superseded[k].astype(str).drop_duplicates()
        b = out[k].astype(str).drop_duplicates()
        missing = a.merge(b, how="left", indicator=True).query("_merge == 'left_only'")
        assert missing.empty, f"{len(missing)} sample_determinations_superseded rows not represented in value_history"
    return out


def build_determinations(pkg: str, out_dir: str, cfg: dict, rank: dict, release_id: str, package_version: str,
                         prev_pkg: str | None, log: dict) -> pd.DataFrame:
    spec = next(t for t in cfg["fact_tables"] if t["file"] == "sample_determinations.parquet")
    default = spec["default_release_added"]
    sd = pd.read_parquet(os.path.join(pkg, "sample_determinations.parquet"))
    vh = pd.read_parquet(os.path.join(pkg, "value_history.parquet"))
    sup_p = os.path.join(pkg, "sample_determinations_superseded.parquet")
    sup = pd.read_parquet(sup_p) if os.path.exists(sup_p) else None
    prev_sd = pd.read_parquet(os.path.join(prev_pkg, "sample_determinations.parquet")) if prev_pkg else None
    ra, prov = seed_determinations(sd, vh, cfg, rank, default, prev_sd, release_id)
    cur = append_cols(sd, ra, cfg, release_id, package_version)
    assert cur.drop(columns=list(COLS)).equals(sd), "sample_determinations changed beyond the appended columns"
    _write(cur, os.path.join(out_dir, "sample_determinations.parquet"))
    ret = retired_rows(list(sd.columns), vh, cfg, sup, default)
    n_gone = 0
    if prev_sd is not None:  # rows of the previous package that disappeared in this release → retired now
        key = ["sample_key", "field_name"]
        gone = prev_sd[~pd.MultiIndex.from_frame(prev_sd[key].astype(str)).isin(pd.MultiIndex.from_frame(sd[key].astype(str)))]
        n_gone = len(gone)
        if n_gone:
            g = gone.copy()
            g["release_added"], g["release_retired"], g["package_added"] = default, release_id, default
            g["retired_reason"] = "row absent from package " + package_version
            g["retired_change_stage"] = "apply_findings"
            ret = pd.concat([ret, g[list(ret.columns)]], ignore_index=True)
    cur_all = cur.copy()
    cur_all["retired_reason"] = pd.Series([pd.NA] * len(cur_all), dtype="string")
    cur_all["retired_change_stage"] = pd.Series([pd.NA] * len(cur_all), dtype="string")
    ret = ret[list(cur_all.columns)].copy()
    for c in ALL_EXTRA:
        ret[c] = ret[c].astype("string")
    for c in sd.columns:  # align dtypes with the current table so the union does not upcast
        try:
            ret[c] = ret[c].astype(sd[c].dtype)
        except (TypeError, ValueError):
            pass
    allrows = pd.concat([cur_all, ret], ignore_index=True)
    _write(allrows, os.path.join(out_dir, cfg["files"]["determinations_all"]))
    log["sample_determinations"] = dict(prov, n_current=len(cur), n_retired=int(len(ret)),
                                        n_retired_from_value_history=int(len(ret) - n_gone), n_retired_gone_this_release=n_gone,
                                        release_added_counts=cur["release_added"].value_counts().sort_index().to_dict(),
                                        release_retired_counts=ret["release_retired"].value_counts().sort_index().to_dict(),
                                        retired_change_stage_counts=ret["retired_change_stage"].value_counts().sort_index().to_dict(),
                                        retired_rule=f"value_history.status in {cfg['retired_statuses']}")
    return cur


# ----------------------------------------------------------------------------------------------- other fact tables
def seed_generic(df: pd.DataFrame, spec: dict, cfg: dict, prev: pd.DataFrame | None, release_id: str, pkg: str) -> pd.Series:
    ra = pd.Series([spec["default_release_added"]] * len(df), index=df.index, dtype=object)
    for ov in spec.get("overrides", []):
        m = pd.Series(True, index=df.index)
        for c, val in ov["match"].items():
            m &= df[c].astype(str) == str(val)
        assert m.sum() == 1, f"override {ov['match']} matched {int(m.sum())} rows in {spec['file']}"
        ra[m] = ov["release_added"]
    if spec.get("seed") == "study_verdict_history":
        svh_p = os.path.join(pkg, "study_verdict_history.parquet")
        if os.path.exists(svh_p):
            svh = pd.read_parquet(svh_p, columns=["is_consolidated", "date"])
            first_pkg_date = pd.Timestamp(cfg["history"][0]["release_date"])
            late = svh[(~svh["is_consolidated"]) & (pd.to_datetime(svh["date"]) > first_pkg_date)]
            assert late.empty, f"{len(late)} verdict-history rows dated after the first package; seeding rule needs a date→release map"
    if prev is not None:
        idx, pidx = _key_index(df, spec["key"]), _key_index(prev, spec["key"])
        ra[~idx.isin(pidx)] = release_id
        dc = spec.get("diff_column")
        if dc and dc in df.columns and dc in prev.columns:
            pv = pd.Series(prev[dc].astype(str).to_numpy(), index=pidx)
            pv = pv[~pv.index.duplicated()]
            changed = (df[dc].astype(str).to_numpy() != pv.reindex(idx).to_numpy()) & idx.isin(pidx)
            ra[changed] = release_id
    return ra


def build_fact_table(pkg: str, out_dir: str, spec: dict, cfg: dict, release_id: str, package_version: str,
                     prev_pkg: str | None, log: dict) -> None:
    src = os.path.join(pkg, spec["file"])
    if not os.path.exists(src):
        log[spec["file"]] = "absent"
        return
    df = _read(src)
    prev = _read(os.path.join(prev_pkg, spec["file"])) if prev_pkg and os.path.exists(os.path.join(prev_pkg, spec["file"])) else None
    ra = seed_generic(df, spec, cfg, prev, release_id, pkg)
    out = append_cols(df, ra, cfg, release_id, package_version)
    assert out.drop(columns=list(COLS)).equals(df), f"{spec['file']} changed beyond the appended columns"
    _write(out, os.path.join(out_dir, spec["file"]))
    if spec.get("csv_twin") and os.path.exists(os.path.join(pkg, spec["csv_twin"])):
        t = _read(os.path.join(pkg, spec["csv_twin"]))
        assert len(t) == len(df), f"{spec['csv_twin']} row count differs from {spec['file']}"
        assert (t[spec["key"]].astype(str).to_numpy() == df[spec["key"]].astype(str).to_numpy()).all(), "csv twin key order differs"
        tw = append_cols(t, ra, cfg, release_id, package_version)
        for c in COLS:
            tw[c] = tw[c].fillna("")
        _write(tw, os.path.join(out_dir, spec["csv_twin"]))
    log[spec["file"]] = dict(n_rows=len(out), release_added_counts=out["release_added"].value_counts().sort_index().to_dict())


# ----------------------------------------------------------------------------------------------- registry
def _registry_row(rid: str, pkg_ver: str, date: str, meta: dict, counts: dict, notes: str) -> dict:
    return {"release_id": rid, "package_version": pkg_ver, "release_date": date or "",
            "data_tag": meta.get("data_tag") or "", "site_tag": meta.get("site_tag") or "", "doi": meta.get("doi") or "",
            **{k: counts.get(k, "") for k in COUNT_KEYS}, "notes_file": notes or ""}


def build_registry(cfg: dict, out_dir: str, release_id: str, package_version: str, release_date: str, counts: dict) -> pd.DataFrame:
    rows = [_registry_row(h["id"], h["package_version"], h["release_date"], h, h.get("counts") or {}, h.get("notes_file", "")) for h in cfg["history"]]
    for r in cfg["releases"]:
        notes = r.get("notes_file") or cfg["files"]["release_notes"].format(release_id=r["release_id"])
        if r["release_id"] == release_id:
            assert r["package_version"] == package_version, f"config/releases.yaml says {release_id} = {r['package_version']}, got {package_version}"
            rows.append(_registry_row(release_id, package_version, release_date, r, counts, notes))
        elif r.get("release_date"):  # an earlier numbered release already cut
            rows.append(_registry_row(r["release_id"], r["package_version"], r["release_date"], r, r.get("counts") or {}, notes))
    reg = pd.DataFrame(rows, columns=cfg["registry_columns"]).astype(str).replace({"nan": "", "None": ""})
    reg.to_csv(os.path.join(out_dir, cfg["files"]["registry"]), index=False)
    return reg


def current_counts(out_dir: str) -> dict:
    smw = pd.read_parquet(os.path.join(out_dir, "sample_metadata_wide.parquet"), columns=["sample_key", "catalog_scope"])
    st = pd.read_parquet(os.path.join(out_dir, "study_metadata_wide.parquet"), columns=["study_accession"])
    sd = pd.read_parquet(os.path.join(out_dir, "sample_determinations.parquet"), columns=["sample_key"])
    c = dict(n_studies_included=len(st), n_samples=len(smw), n_determinations_current=len(sd),
             n_catalog_scope=int(smw["catalog_scope"].fillna(False).astype(bool).sum()))
    sp = os.path.join(out_dir, "sandpiper_sample_summary.parquet")
    if os.path.exists(sp):
        v = pd.read_parquet(sp, columns=["sandpiper_version"])["sandpiper_version"].dropna().unique()
        c["sandpiper_version"] = str(v[0]) if len(v) == 1 else ";".join(sorted(map(str, v)))
    return c


def run(package: str, out_dir: str, release_id: str, package_version: str, previous_package_version: str,
        previous_package: str | None = None, release_date: str | None = None, config_path: str | None = None) -> dict:
    cfg = load_config(config_path)
    assert re.match(cfg["release_id"]["regex"], release_id), f"release id {release_id!r} does not match {cfg['release_id']['regex']}"
    rank = {r: i for i, r in enumerate(release_order(cfg))}
    assert release_id in rank, f"{release_id} is not declared in config/releases.yaml: releases"
    known = [h["package_version"] for h in cfg["history"]] + [r["package_version"] for r in cfg["releases"]]
    assert previous_package_version in known, f"previous package {previous_package_version} unknown to config/releases.yaml"
    os.makedirs(out_dir, exist_ok=True)
    if os.path.abspath(package) != os.path.abspath(out_dir):
        for fn in sorted(os.listdir(package)):
            p = os.path.join(package, fn)
            if os.path.isfile(p):
                shutil.copy2(p, os.path.join(out_dir, fn))
    log: dict = {"release_id": release_id, "package_version": package_version, "previous_package_version": previous_package_version}
    build_determinations(package, out_dir, cfg, rank, release_id, package_version, previous_package, log)
    for spec in cfg["fact_tables"]:
        if spec["file"] != "sample_determinations.parquet":
            build_fact_table(package, out_dir, spec, cfg, release_id, package_version, previous_package, log)
    counts = current_counts(out_dir)
    if not release_date:
        vj = os.path.join(package, "VERSION.json")
        release_date = json.load(open(vj)).get("build_date") if os.path.exists(vj) else None
    assert release_date, "--release-date required (no VERSION.json build_date to fall back on); never wall-clock"
    reg = build_registry(cfg, out_dir, release_id, package_version, release_date, counts)
    used = set()
    for v in log.values():
        if isinstance(v, dict):
            used |= set(v.get("release_added_counts", {})) | set(v.get("release_retired_counts", {}))
    missing = used - set(reg["release_id"])
    assert not missing, f"release ids used in columns but absent from releases.csv: {sorted(missing)}"
    log["counts"], log["registry_rows"], log["release_date"] = counts, len(reg), release_date
    json.dump(log, open(os.path.join(out_dir, "bitemporal_log.json"), "w"), indent=1, sort_keys=True, default=str)
    return log


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--package", required=True, help="unpacked package dir (input tables)")
    ap.add_argument("--out", required=True, help="output dir (may equal --package: tables are rewritten in place)")
    ap.add_argument("--release-id", required=True)
    ap.add_argument("--package-version", required=True)
    ap.add_argument("--previous-package-version", required=True)
    ap.add_argument("--previous-package", default=None, help="unpacked PREVIOUS package dir; enables new/gone row detection")
    ap.add_argument("--release-date", default=None, help="YYYY-MM-DD (default: --package VERSION.json build_date)")
    ap.add_argument("--config", default=None)
    a = ap.parse_args(argv)
    log = run(a.package, a.out, a.release_id, a.package_version, a.previous_package_version, a.previous_package, a.release_date, a.config)
    print(json.dumps({k: log[k] for k in ("release_id", "package_version", "release_date", "counts", "registry_rows")}
                     | {"determinations": {k: v for k, v in log["sample_determinations"].items() if not isinstance(v, dict)}}, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())

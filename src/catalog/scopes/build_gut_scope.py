"""Curated scope `gut_all` (config/packs/gut.yaml): assemble gut_sample_determinations / gut_sample_metadata_wide / gut_studies.

Sources, in precedence order per (sample, field):
  0. the curated infant catalog (sample_determinations.parquet current rows of the 389 included studies; src_track infant_catalog) — wins
  1. R1 archive attributes: registry_biosamples (normalised age / sex / country) + gut_r1_determinations (bmi, antibiotics, subject,
     timepoint, health_condition_detail …)
  2. R2 supplementary tables (gut_r2_determinations_shard_*.parquet)
  3. R3 (none in v1)
  4. R4 abstract / study-description statements (gut_r4_determinations_shard_*.parquet, scope study_all) expanded to the study's samples
     that have no sample-level value for the field (confidence ≤ 0.5, evidence_limited_to_abstract = 1)
health_condition codes come from gut_health_condition_map (key, value → code) applied to health_condition_detail rows; antibiotic codes
from gut_antibiotic_map. Every row keeps the determination schema of the infant tables. Deterministic; no LLM calls.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

import pandas as pd
import yaml

DET_COLS = ["sample_key", "field_name", "study_accession", "field_value", "value_normalized", "confidence", "evidence_source", "evidence_locator",
            "evidence_quote", "evidence_limited_to_abstract", "determined_by", "route", "scope", "parse_note", "group_audit", "src_track",
            "release_added", "release_retired", "package_added"]
PACK_FIELDS = ["age_at_collection_days", "sex", "bmi", "country", "health_condition", "health_condition_detail", "antibiotic_exposure", "subject_id", "timepoint_label"]
INFANT_ONLY = ["delivery_mode", "feeding_mode", "preterm_status", "gestational_age_weeks", "birth_weight_grams", "maternal_antibiotics", "probiotic_exposure", "hmo_supplementation", "nec_status"]
ROUTE_RANK = {"R1": 1, "R2": 2, "R3": 3, "R4": 4}
SRC = "gut_all_v1"
STAGE_TO_CAT = {"neonate": "neonate", "infant": "infant", "child": "child", "adolescent": "adolescent", "adult": "adult", "elderly": "elderly"}


def _load_pack(cfg_dir):
    return yaml.safe_load(open(os.path.join(cfg_dir, "packs", "gut.yaml"), encoding="utf-8"))


def _q12(v):
    s = "" if v is None else str(v)
    return " ".join(s.split()[:12])[:200]


def _row(sample, field, study, value, norm, conf, src, loc, quote, route, by, note="", scope="sample", limited=0, release_id="", pv=""):
    return dict(sample_key=sample, field_name=field, study_accession=study, field_value=str(value), value_normalized=None if norm is None else str(norm),
                confidence=float(conf), evidence_source=src, evidence_locator=loc, evidence_quote=_q12(quote), evidence_limited_to_abstract=float(limited),
                determined_by=by, route=route, scope=scope, parse_note=note, group_audit=None, src_track=SRC, release_added=release_id, release_retired=None, package_added=pv)


def age_category(days, pack):
    if days is None or pd.isna(days):
        return None
    for k, (lo, hi) in pack["age_categories"].items():
        if days >= lo and (hi is None or days <= hi):
            return k
    return None


def rows_from_registry_biosamples(bio: pd.DataFrame, release_id: str, pv: str) -> list[dict]:
    """R1 rows from the registry's normalised BioSample fields (evidence = the raw attribute the code came from)."""
    out = []
    for r in bio.itertuples(index=False):
        s, st = r.sample_accession, r.study_accession
        if pd.notna(r.age_days):
            out.append(_row(s, "age_at_collection_days", st, r.age_raw_value, round(float(r.age_days), 1), 0.85, f"sample.attr.{r.age_raw_key}", "biosample_attr", r.age_raw_value, "R1", "registry_norm_v1:age", "utility-model normalisation of the attribute pair", release_id=release_id, pv=pv))
        if isinstance(r.sex, str) and r.sex in ("female", "male"):
            out.append(_row(s, "sex", st, r.sex_raw_value, r.sex, 0.9, f"sample.attr.{r.sex_raw_key}", "biosample_attr", r.sex_raw_value, "R1", "registry_norm_v1:sex", release_id=release_id, pv=pv))
        if isinstance(r.country_iso2, str) and len(r.country_iso2) == 2:
            out.append(_row(s, "country", st, r.country_raw_value, r.country_iso2, 0.9, f"sample.attr.{r.country_raw_key}", "biosample_attr", r.country_raw_value, "R1", "registry_norm_v1:country", release_id=release_id, pv=pv))
    return out


def load_any(pat: str | None) -> pd.DataFrame:
    if not pat:
        return pd.DataFrame(columns=DET_COLS)
    fs = sorted(glob.glob(pat)) if "*" in pat else ([pat] if os.path.exists(pat) else [])
    return pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True).reindex(columns=DET_COLS) if fs else pd.DataFrame(columns=DET_COLS)


def _attr_key(src) -> str | None:
    s = str(src)
    return s[len("sample.attr."):] if s.startswith("sample.attr.") else None


def apply_condition_maps(det: pd.DataFrame, cond_map: pd.DataFrame | None, abx_map: pd.DataFrame | None, release_id, pv) -> pd.DataFrame:
    """health_condition_detail rows (raw text) → health_condition code rows via the normalisation map (key + value); antibiotic raw
    rows without a normalised value → yes/no via the antibiotic map."""
    extra = []
    if cond_map is not None and len(cond_map):
        cm = cond_map.dropna(subset=["health_condition"])
        cm = cm[(cm.health_condition != "unknown") & (cm.confidence.fillna(0) >= 0.5)]
        key = {(str(k), str(v)): (c, cf, m) for k, v, c, cf, m in zip(cm.attr_key_norm, cm.attr_value, cm.health_condition, cm.confidence, cm.method)}
        d = det[det.field_name == "health_condition_detail"]
        for r in d.itertuples(index=False):
            k = _attr_key(r.evidence_source)
            hit = key.get((k, str(r.field_value))) if k else None
            if hit:
                c, cf, m = hit
                extra.append(_row(r.sample_key, "health_condition", r.study_accession, r.field_value, c, min(float(r.confidence), float(cf)), r.evidence_source, r.evidence_locator, r.evidence_quote, r.route, f"gut_condition_map:{m}", "code from config/vocab/health_conditions.yaml", release_id=release_id, pv=pv))
    if abx_map is not None and len(abx_map):
        am = abx_map[abx_map.antibiotic_exposure.isin(["yes", "no"]) & (abx_map.confidence.fillna(0) >= 0.5)]
        key = {(str(k), str(v)): (c, cf, m) for k, v, c, cf, m in zip(am.attr_key_norm, am.attr_value, am.antibiotic_exposure, am.confidence, am.method)}
        d = det[(det.field_name == "antibiotic_exposure") & det.value_normalized.isna()]
        for r in d.itertuples(index=False):
            k = _attr_key(r.evidence_source)
            hit = key.get((k, str(r.field_value))) if k else None
            if hit:
                c, cf, m = hit
                extra.append(_row(r.sample_key, "antibiotic_exposure", r.study_accession, r.field_value, c, min(float(r.confidence), float(cf)), r.evidence_source, r.evidence_locator, r.evidence_quote, r.route, f"gut_antibiotic_map:{m}", release_id=release_id, pv=pv))
    return pd.concat([det, pd.DataFrame(extra, columns=DET_COLS)], ignore_index=True) if extra else det


def resolve(det: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """One current row per (sample, field): precedence infant catalog > R1 > R2 > R3 > R4, then confidence. Losers whose normalised
    value differs from the winner are returned as conflicts."""
    d = det[det.value_normalized.notna()].copy()
    d["_rank"] = d.route.map(ROUTE_RANK).fillna(9)
    d.loc[d.src_track == "infant_catalog", "_rank"] = 0
    d = d.sort_values(["sample_key", "field_name", "_rank", "confidence"], ascending=[True, True, True, False], kind="mergesort")
    keep = d.drop_duplicates(["sample_key", "field_name"], keep="first")
    lost = d.loc[d.index.difference(keep.index)]
    win = keep.set_index(["sample_key", "field_name"]).value_normalized
    idx = pd.MultiIndex.from_arrays([lost.sample_key, lost.field_name])
    lost = lost.assign(_win=win.reindex(idx).values)
    conflicts = lost[lost.value_normalized.astype(str) != lost._win.astype(str)].drop(columns=["_win", "_rank"])
    return keep.drop(columns=["_rank"]), conflicts


def expand_study_all(det_sample: pd.DataFrame, det_study: pd.DataFrame, samples: pd.DataFrame) -> pd.DataFrame:
    """study_all statements → one row per study sample lacking a sample-level value for that field."""
    if det_study.empty:
        return pd.DataFrame(columns=DET_COLS)
    have = set(zip(det_sample.sample_key, det_sample.field_name))
    per_study = samples.groupby("study_accession").sample_key.apply(list)
    rows = []
    for r in det_study.to_dict("records"):
        for s in per_study.get(r["study_accession"], []):
            if (s, r["field_name"]) in have:
                continue
            rows.append(dict(r, sample_key=s, scope="sample", parse_note=(str(r.get("parse_note") or "") + " | expanded from study_all").strip(" |")))
    return pd.DataFrame(rows, columns=DET_COLS) if rows else pd.DataFrame(columns=DET_COLS)


def build(a):
    cfg_dir = os.environ.get("CATALOG_CONFIG_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "..", "config"))
    pack = _load_pack(cfg_dir)
    rid, pv = a.release_id, a.package_version
    studies = pd.read_parquet(a.studies)
    reg = pd.read_parquet(a.registry_studies) if a.registry_studies else studies
    gut_acc = set(studies.study_accession)
    infant_acc = set(studies.loc[studies.in_infant_catalog == "include", "study_accession"]) if "in_infant_catalog" in studies.columns else set()

    # ---- samples: registry_biosamples of the non-infant gut studies + the curated infant samples
    bio = pd.read_parquet(a.biosamples)
    bio = bio[bio.study_accession.isin(gut_acc - infant_acc)]
    if "release_retired" in bio.columns:
        bio = bio[bio.release_retired.isna()]
    wide0 = pd.read_parquet(os.path.join(a.package, "sample_metadata_wide.parquet"))
    wide0 = wide0[wide0.study_accession.isin(infant_acc)]
    # BioSamples shared between BioProjects (umbrella / re-deposited studies): the curated infant assignment wins, so the infant
    # rows come first and the registry rows of the same sample are dropped
    samples = pd.concat([
        pd.DataFrame(dict(sample_key=wide0.sample_key.values, study_accession=wide0.study_accession.values, biosample_accession=wide0.biosample_accession.values, secondary_sample=wide0.secondary_sample.values,
                          sample_unit=wide0.sample_unit.values, body_site_code=wide0.body_site_class.map({"primary": "gut_stool", "unknown": None, "excluded": "other_site", "linked": "other_site"}).values,
                          sample_life_stage=None, curated_source="infant_catalog")),
        pd.DataFrame(dict(sample_key=bio.sample_accession.values, study_accession=bio.study_accession.values, biosample_accession=bio.sample_accession.values, secondary_sample=None,
                          sample_unit="biosample", body_site_code=bio.body_site_code.values, sample_life_stage=bio.life_stage.values, curated_source=SRC)),
    ], ignore_index=True).drop_duplicates("sample_key", keep="first")
    bio = bio[bio.sample_accession.isin(set(samples.loc[samples.curated_source == SRC, "sample_key"]))]
    samples["in_infant_catalog"] = samples.study_accession.isin(infant_acc)

    # ---- determinations
    parts = [pd.DataFrame(rows_from_registry_biosamples(bio, rid, pv), columns=DET_COLS), load_any(a.r1), load_any(a.r1_extra), load_any(a.r2_glob), load_any(a.r4_glob)]
    det0 = pd.read_parquet(os.path.join(a.package, "sample_determinations.parquet"))
    det0 = det0[det0.study_accession.isin(infant_acc) & det0.field_name.isin(PACK_FIELDS + INFANT_ONLY)]
    if "release_retired" in det0.columns:
        det0 = det0[det0.release_retired.isna()]
    det0 = det0.assign(src_track="infant_catalog").reindex(columns=DET_COLS)
    det = pd.concat(parts + [det0], ignore_index=True)
    det = det[det.study_accession.isin(gut_acc)]
    cond = pd.read_parquet(a.condition_map) if a.condition_map and os.path.exists(a.condition_map) else None
    abx = pd.read_parquet(a.antibiotic_map) if a.antibiotic_map and os.path.exists(a.antibiotic_map) else None
    det = apply_condition_maps(det, cond, abx, rid, pv)
    # 'unknown' / placeholder codes are not determinations (unknown stays unknown = no row); keep raw detail text
    unk = det.value_normalized.astype("string").str.lower().isin(["unknown", "unknown_age", "unknown_site", "none", "nan", ""]) & (det.field_name != "health_condition_detail")
    det = det[~unk.fillna(False)]
    # routes allowed per field (config/packs/gut.yaml fields.<f>.routes); infant-catalog rows are exempt (their own rules applied)
    allowed = {f: set(v.get("routes", ["R1", "R2", "R3", "R4"])) for f, v in pack["fields"].items()}
    ok_route = [(r in allowed.get(f, {"R1", "R2", "R3", "R4"})) or (t == "infant_catalog") for f, r, t in zip(det.field_name, det.route, det.src_track)]
    det = det[pd.Series(ok_route, index=det.index)]
    det_study = det[det.scope == "study_all"]
    det_sample = det[det.scope != "study_all"]
    det_sample = det_sample[det_sample.sample_key.isin(set(samples.sample_key))]
    det_sample, conflicts = resolve(det_sample)
    det_r4 = expand_study_all(det_sample, det_study, samples[~samples.in_infant_catalog])
    det_all = pd.concat([det_sample, det_r4], ignore_index=True)
    det_all = det_all[det_all.field_name.isin(PACK_FIELDS + INFANT_ONLY)].copy()
    inf = det_all.src_track == "infant_catalog"
    det_all.loc[~inf, "release_added"] = rid
    det_all.loc[~inf, "package_added"] = pv
    det_all["release_retired"] = None

    # ---- wide
    piv = det_all.pivot_table(index="sample_key", columns="field_name", values="value_normalized", aggfunc="first")
    conf = det_all.pivot_table(index="sample_key", columns="field_name", values="confidence", aggfunc="first")
    route = det_all.pivot_table(index="sample_key", columns="field_name", values="route", aggfunc="first")
    w = samples.set_index("sample_key")
    for f in PACK_FIELDS + INFANT_ONLY:
        w[f] = piv[f] if f in piv.columns else None
        if f in PACK_FIELDS:
            w[f + "__confidence"] = conf[f] if f in conf.columns else None
            w[f + "__route"] = route[f] if f in route.columns else None
    w["age_at_collection_days"] = pd.to_numeric(w["age_at_collection_days"], errors="coerce")
    w["bmi"] = pd.to_numeric(w["bmi"], errors="coerce")
    st_stage = reg.set_index("study_accession").life_stage_primary if "life_stage_primary" in reg.columns else pd.Series(dtype=str)
    cat_age = w.age_at_collection_days.map(lambda d: age_category(d, pack))
    cat_stage = w.sample_life_stage.map(STAGE_TO_CAT)
    r4_stage = det_study[det_study.field_name == "life_stage"].sort_values("confidence", ascending=False).drop_duplicates("study_accession").set_index("study_accession").value_normalized
    cat_r4 = w.study_accession.map(r4_stage).map(STAGE_TO_CAT)
    cat_study = w.study_accession.map(st_stage).map(STAGE_TO_CAT)
    scope0 = wide0.set_index("sample_key").age_scope
    cat_inf = pd.Series(w.index.map(scope0), index=w.index).map(lambda v: "infant" if v in ("infant_evidenced", "study_all_infant") else ("adult" if v == "adult_flagged" else None))
    is_inf = w.in_infant_catalog
    # infant-catalog rows: the curated age_scope is authoritative (no fall-back to the study's life stage — the catalog deliberately
    # leaves mixed-age / no-estimate samples unknown); registry rows: age → sample life stage → study life stage
    cat_curated = cat_age.fillna(cat_inf)
    cat_registry = cat_age.fillna(cat_stage).fillna(cat_r4).fillna(cat_study)
    w["age_category"] = cat_curated.where(is_inf, cat_registry).fillna("unknown")
    basis = pd.Series("unknown", index=w.index)
    basis = basis.mask(~is_inf & cat_study.notna(), "study_life_stage").mask(~is_inf & cat_r4.notna(), "r4_abstract_life_stage").mask(~is_inf & cat_stage.notna(), "sample_life_stage").mask(is_inf & cat_inf.notna(), "infant_catalog_age_scope").mask(cat_age.notna(), "age_at_collection_days")
    w["age_category_basis"] = basis
    w["body_site_class"] = w.body_site_code.map(lambda c: "primary" if c == "gut_stool" else ("unknown" if (c is None or pd.isna(c) or c == "unknown_site") else "excluded"))
    w["body_site_basis"] = w.body_site_code.map(lambda c: "sample_attribute" if isinstance(c, str) and c not in ("unknown_site",) else "none")
    # a sample without any site attribute in a study whose ONLY registry body site is gut_stool is a gut sample by study design
    st_sites = reg.set_index("study_accession").body_sites if "body_sites" in reg.columns else pd.Series(dtype=str)
    single_gut = w.study_accession.map(st_sites).fillna("") == "gut_stool"
    no_attr = w.body_site_code.isna() | (w.body_site_code == "unknown_site")
    w.loc[~is_inf & single_gut & no_attr, "body_site_class"] = "primary"
    w.loc[~is_inf & single_gut & no_attr, "body_site_basis"] = "study_single_site"
    bsc0 = wide0.set_index("sample_key").body_site_class
    m0 = w.index.isin(bsc0.index)
    w.loc[m0, "body_site_class"] = pd.Series(w.index[m0].map(bsc0), index=w.index[m0])
    # infant_scope == the infant catalog's catalog_scope rule exactly (age_scope infant_evidenced/study_all_infant AND body site primary/unknown)
    inf_scope0 = pd.Series(w.index.map(scope0), index=w.index).isin(["infant_evidenced", "study_all_infant"])
    w["infant_scope"] = is_inf & inf_scope0 & w.body_site_class.isin(["primary", "unknown"])
    w["n_fields_with_value"] = w[PACK_FIELDS].notna().sum(axis=1)
    w["release_added"], w["release_retired"], w["package_added"] = rid, None, pv
    w = w.reset_index()

    # ---- studies
    g = w.groupby("study_accession")
    cov = pd.DataFrame({f"cov_{f}": g[f].apply(lambda s: round(float(s.notna().mean()), 3)) for f in PACK_FIELDS})
    gs = studies.set_index("study_accession").join(cov, how="left")
    gs["n_samples_curated"] = g.size()
    gs["age_categories"] = g.age_category.apply(lambda s: json.dumps(s.value_counts().to_dict()))
    gs["health_conditions"] = g.health_condition.apply(lambda s: json.dumps(s.dropna().value_counts().head(6).to_dict()))
    gs["curated_depth"] = det_all.groupby("study_accession").route.apply(lambda s: ";".join(sorted(set(s))))
    gs["curated_source"] = ["infant_catalog" if x in infant_acc else SRC for x in gs.index]
    gs["n_samples_curated"] = gs.n_samples_curated.fillna(0).astype(int)
    gs["release_added"], gs["release_retired"], gs["package_added"] = rid, None, pv
    gs = gs.reset_index()

    os.makedirs(a.out, exist_ok=True)
    det_all = det_all.reindex(columns=DET_COLS)
    if a.previous_dir:
        from catalog.registry.build_registry import carry_release_columns
        for name, key, df_ref in ((pack["tables"]["determinations"], ["sample_key", "field_name"], "det"), (pack["tables"]["samples_wide"], ["sample_key"], "w"), (pack["tables"]["studies"], ["study_accession"], "gs")):
            prev_p = os.path.join(a.previous_dir, name)
            if os.path.exists(prev_p):
                prev = pd.read_parquet(prev_p)
                if df_ref == "det":
                    det_all = carry_release_columns(det_all, prev, key, rid)
                elif df_ref == "w":
                    w = carry_release_columns(w, prev, key, rid)
                else:
                    gs = carry_release_columns(gs, prev, key, rid)
    det_all.to_parquet(os.path.join(a.out, pack["tables"]["determinations"]), index=False)
    w.to_parquet(os.path.join(a.out, pack["tables"]["samples_wide"]), index=False)
    gs.to_parquet(os.path.join(a.out, pack["tables"]["studies"]), index=False)
    conflicts.to_parquet(os.path.join(a.out, "gut_sample_determinations_conflicts.parquet"), index=False)
    summary = dict(n_studies=int(len(gs)), n_samples=int(len(w)), n_determinations=int(len(det_all)), n_conflicts=int(len(conflicts)),
                   by_source=w.curated_source.value_counts().to_dict(), age_category=w.age_category.value_counts().to_dict(),
                   coverage={f: round(float(w[f].notna().mean()), 4) for f in PACK_FIELDS}, routes=det_all.route.value_counts().to_dict(),
                   n_infant_scope=int(w.infant_scope.sum()), health_condition=w.health_condition.value_counts().head(12).to_dict())
    if a.summary:
        json.dump(summary, open(a.summary, "w"), indent=1)
    print(json.dumps(summary))
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--studies", required=True, help="gut study list (registry columns + in_infant_catalog)")
    ap.add_argument("--registry-studies"), ap.add_argument("--biosamples", required=True), ap.add_argument("--package", required=True, help="previous package dir (infant curated tables)")
    ap.add_argument("--r1"), ap.add_argument("--r1-extra", help="additional R1 determination files (glob), e.g. the condition/antibiotic expansion"), ap.add_argument("--r2-glob"), ap.add_argument("--r4-glob"), ap.add_argument("--condition-map"), ap.add_argument("--antibiotic-map")
    ap.add_argument("--out", required=True), ap.add_argument("--summary"), ap.add_argument("--release-id", default="R2026.7"), ap.add_argument("--package-version", default="1.8.0")
    ap.add_argument("--previous-dir", help="previous package dir: gut_* tables there provide release_added / retirements")
    build(ap.parse_args(argv))
    return 0


if __name__ == "__main__":
    sys.exit(main())

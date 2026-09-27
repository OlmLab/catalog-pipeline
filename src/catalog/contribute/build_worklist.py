#!/usr/bin/env python
"""build_worklist.py — the read-only community-contribution worklist (MATURITY_PLAN §3.2; config/contribute.yaml).

    python -m catalog.contribute.build_worklist --package build/package --inputs data/inputs/contribute \
        --out build/package --release-id R2026.2 --package-version 1.4.0 [--report build/WORKLIST_REPORT.md]

Writes contribute_worklist.csv (one row per OPEN included/uncertain study, ranked) and contribute_worklist_fields.csv
(study × six fields). Deterministic: no network, no LLM; every value is traceable to an input column (docs/CONTRIBUTE.md).

Package inputs (--package): universe_studies_all.parquet, study_metadata_wide.parquet, study_paper_links.csv,
human_review_queue.csv, sample_metadata_wide.parquet.
Artifact inputs (--inputs; config/inputs.json group `contribute`): extraction_worklist_v3.csv, recoverability.parquet,
RESCUE_REPORT_v2.md, r2_rescue_studies.csv, supp_inventory.parquet, controlled_access_registry.csv.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from urllib.parse import quote

import numpy as np
import pandas as pd
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
CONFIG_DIR = os.environ.get("CATALOG_CONFIG_DIR", os.path.join(REPO, "config"))

INPUT_FILES = {
    "worklist": "extraction_worklist_v3.csv",
    "recoverability": "recoverability.parquet",
    "rescue_report": "RESCUE_REPORT_v2.md",
    "r2_rescue": "r2_rescue_studies.csv",
    "supp_inventory": "supp_inventory.parquet",
    "controlled": "controlled_access_registry.csv",
}
TIER_RANK = {"R1": 1, "R2": 2, "R3": 3, "R4": 4, "R0": 5}


def load_config(path: str | None = None) -> dict:
    return yaml.safe_load(open(path or os.path.join(CONFIG_DIR, "contribute.yaml"), encoding="utf-8"))


def _read(path: str) -> pd.DataFrame:
    return pd.read_parquet(path) if path.endswith(".parquet") else pd.read_csv(path, low_memory=False)


def _clip(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _log10(n: int) -> float:
    return math.log10(int(n) + 1)


# ----------------------------------------------------------------------------------------------------------------------
# RESCUE_REPORT_v2.md parsing: (study_accession → id_form, status)
def parse_rescue_report(text: str) -> pd.DataFrame:
    """Per-study rows from the two structured blocks of RESCUE_REPORT_v2.md.

    * `## Per-study table` rows: | study | n_samples | tables (cand / new accepted) | methods | fields gained | status |
    * `## Unprocessed / no-yield ...` bullets: `* PRJ… (n samples): k candidate tables; sid_col forms [...]`
    """
    rows: dict[str, dict] = {}
    for m in re.finditer(r"^\|\s*(PRJ\w+)\s*\|\s*(\d+)\s*\|\s*([^|]*)\|\s*([^|]*)\|\s*([^|]*)\|\s*([^|]*)\|\s*$", text, re.M):
        acc = m.group(1)
        rows[acc] = {"study_accession": acc, "rescue_n_samples": int(m.group(2)), "rescue_tables": m.group(3).strip(),
                     "rescue_methods": m.group(4).strip(), "rescue_fields_gained": m.group(5).strip(),
                     "rescue_status": m.group(6).strip(), "id_form": None, "n_candidate_tables": None}
    for m in re.finditer(r"^\*\s*(PRJ\w+)\s*\((\d+) samples\):\s*(.*)$", text, re.M):
        acc, tail = m.group(1), m.group(3).strip()
        r = rows.setdefault(acc, {"study_accession": acc, "rescue_n_samples": int(m.group(2)), "rescue_tables": "",
                                  "rescue_methods": "", "rescue_fields_gained": "", "rescue_status": "", "id_form": None,
                                  "n_candidate_tables": None})
        mc = re.match(r"(\d+) candidate tables;\s*sid_col forms \[(.*)\]", tail)
        if mc:
            r["n_candidate_tables"] = int(mc.group(1))
            forms = [f.strip() for f in re.findall(r"'((?:[^'\\]|\\.)*)'", mc.group(2))]
            r["id_form"] = ", ".join(f for f in forms if f)
        elif tail.startswith("no candidate table"):
            r["n_candidate_tables"] = 0
            r["id_form"] = "no candidate table in supp_inventory"
    return pd.DataFrame(list(rows.values()))


# ----------------------------------------------------------------------------------------------------------------------
def coverage_tables(sample_wide: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per-study coverage of the six fields on catalog_scope, plus the body-site-scope fallback."""
    fields = {k: v["field_name"] for k, v in cfg["fields"].items()}
    cs = sample_wide[sample_wide["catalog_scope"].fillna(False).astype(bool)]
    bs = sample_wide[sample_wide["body_site_class"].isin(["primary", "unknown"])]

    def agg(df: pd.DataFrame, tag: str) -> pd.DataFrame:
        g = df.groupby("study_accession")
        out = pd.DataFrame({f"n_with_value_{k}": g[f].apply(lambda s: int(s.notna().sum())) for k, f in fields.items()})
        out[f"n_{tag}"] = g.size()
        for k in fields:
            out[f"coverage_{k}"] = (out[f"n_with_value_{k}"] / out[f"n_{tag}"]).where(out[f"n_{tag}"] > 0, 0.0)
        return out

    return agg(cs, "catalog_scope"), agg(bs, "body_site_scope")


def controlled_studies(reg: pd.DataFrame, uni: pd.DataFrame, links: pd.DataFrame, ew: pd.DataFrame) -> dict[str, str]:
    """study_accession → source string for every study judged controlled-access."""
    out: dict[str, str] = {}
    ctrl = reg[~reg["tier"].astype(str).str.startswith("open")]
    accs = set(uni["study_accession"])
    for _, r in ctrl.iterrows():
        a = str(r["accession"])
        if a in accs:
            out.setdefault(a, f"registry accession {a} ({r['tier']})")
    coh = ctrl[ctrl["accession_type"] == "cohort"]
    if len(coh):
        for _, u in uni[uni["cohort_id"].isin(set(coh["accession"]))].iterrows():
            out.setdefault(u["study_accession"], f"registry cohort {u['cohort_id']} (non_remediable_controlled)")
    # NOTE: registry paper_ids are NOT used: a paper citing an EGA/dbGaP dataset may also reuse many open BioProjects
    # (one GSA paper links 17 catalog studies); a BioProject's sequence data are open by construction — only the
    # cohort-level registration (cohorts.csv controlled_access/named) or an explicit study flag marks it controlled.
    for _, e in ew[ew["controlled_access"].fillna(False).astype(bool)].iterrows():
        out.setdefault(e["study_accession"], "extraction_worklist.controlled_access")
    for _, u in uni[uni["controlled_access"].fillna(False).astype(bool)].iterrows():
        out.setdefault(u["study_accession"], "universe_studies_all.controlled_access")
    return out


def best_tiers(rec: pd.DataFrame) -> pd.DataFrame:
    """study × field → best recoverability tier, evidence, note (recoverability.parquet; R1 best … R0 none)."""
    r = rec.copy()
    r["rank"] = r["tier"].map(TIER_RANK).fillna(9)
    r = r.sort_values(["study_accession", "field", "rank", "confidence"], ascending=[True, True, True, False])
    r = r.drop_duplicates(["study_accession", "field"], keep="first")
    return r.set_index(["study_accession", "field"])[["tier", "evidence", "note", "source_paper_id", "source_file"]]


def _evidence_text(ev, note, tier) -> str:
    parts = []
    try:
        j = json.loads(ev) if isinstance(ev, str) else (list(ev) if ev is not None else [])
    except Exception:  # noqa: BLE001
        j = []
    if j:
        e = j[0]
        parts.append(f"{e.get('source', '')}: {e.get('quote', '')}".strip(": "))
    if note is not None and str(note) not in ("nan", "None", ""):
        parts.append(str(note))
    return f"{tier} " + " | ".join(parts) if parts else str(tier)


ID_LIKE = re.compile(r"(sample|subject|specimen|infant|participant|patient|baby|child|\bid\b|_id|code|name)", re.I)
ACCESSION_LIKE = re.compile(r"^(biosample|run|run id|accession|sample accession|genome.*|assembly id|era?\d+.*|srr\d+.*|drr\d+.*)$", re.I)


def pick_id_form(id_form: str | None, default: str) -> str:
    """Most identifier-like of the RESCUE_REPORT sid_col forms (comma-joined), skipping accession-style and statistic headers."""
    if not id_form or id_form.startswith("no candidate table"):
        return default
    forms = [f.strip() for f in id_form.split(",") if f.strip()]
    cands = [f for f in forms if ID_LIKE.search(f) and not ACCESSION_LIKE.match(f)]
    if cands:
        return cands[0]
    rest = [f for f in forms if not ACCESSION_LIKE.match(f)]
    return rest[0] if rest else default


def issue_url_for(cfg: dict, accession: str, contribution_type: str, release_id: str) -> str:
    title = cfg["issue"]["title_template"].format(accession=accession, contribution_type=contribution_type)
    return cfg["issue"]["url_template"].format(repo=cfg["issue"]["repo"], template=cfg["issue"]["template"],
                                                labels=cfg["issue"]["labels"], title=quote(title, safe=""),
                                                accession=accession, contribution_type=contribution_type, release_id=release_id)


def priority_score(cfg: dict, coverages: dict[str, float], missing: list[str], n_catalog_scope: int) -> float:
    return sum(float(cfg["fields"][k]["weight"]) * (1.0 - float(coverages[k])) for k in missing) * _log10(n_catalog_scope)


# ----------------------------------------------------------------------------------------------------------------------
def build(package: str, inputs: str, cfg: dict, release_id: str, package_version: str) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    P = lambda f: os.path.join(package, f)  # noqa: E731
    I = lambda k: os.path.join(inputs, INPUT_FILES[k])  # noqa: E731
    uni = pd.read_parquet(P("universe_studies_all.parquet"))
    smw = pd.read_parquet(P("study_metadata_wide.parquet"), columns=["study_accession", "ena_url", "ncbi_url"]).set_index("study_accession")
    links = pd.read_csv(P("study_paper_links.csv"), dtype={"paper_id": str, "pmid": str})
    hrq = pd.read_csv(P("human_review_queue.csv"), low_memory=False)
    fields_short = list(cfg["field_order"])
    fnames = [cfg["fields"][k]["field_name"] for k in fields_short]
    sw = pd.read_parquet(P("sample_metadata_wide.parquet"), columns=["sample_key", "study_accession", "catalog_scope", "body_site_class"] + fnames)
    ew = _read(I("worklist"))
    rec = _read(I("recoverability"))
    rescue = parse_rescue_report(open(I("rescue_report"), encoding="utf-8").read())
    r2 = _read(I("r2_rescue"))
    si = _read(I("supp_inventory"))
    reg = _read(I("controlled"))

    thr = float(cfg["missing_threshold"])
    cov_cs, cov_bs = coverage_tables(sw, cfg)
    cand = uni[uni["triage_verdict"].isin(["include", "uncertain"])].copy()
    assert cand["study_accession"].is_unique
    cand = cand.set_index("study_accession")
    n_cs = cov_cs["n_catalog_scope"].reindex(cand.index).fillna(0).astype(int)
    use_fallback = (n_cs == 0).to_numpy()
    cov = pd.DataFrame(index=cand.index)
    for k in fields_short:
        a = cov_cs[f"coverage_{k}"].reindex(cand.index).fillna(0.0).to_numpy()
        b = cov_bs[f"coverage_{k}"].reindex(cand.index).fillna(0.0).to_numpy()
        cov[f"coverage_{k}"] = np.where(use_fallback, b, a).astype(float)
        na = cov_cs[f"n_with_value_{k}"].reindex(cand.index).fillna(0).to_numpy()
        nb = cov_bs[f"n_with_value_{k}"].reindex(cand.index).fillna(0).to_numpy()
        cov[f"n_with_value_{k}"] = np.where(use_fallback, nb, na).astype(int)
    cov["coverage_scope"] = np.where(use_fallback, cfg["scopes"]["fallback"], cfg["scopes"]["primary"])
    cov["n_scope"] = np.where(use_fallback, cov_bs["n_body_site_scope"].reindex(cand.index).fillna(0).to_numpy(), n_cs.to_numpy()).astype(int)
    missing = pd.DataFrame({k: cov[f"coverage_{k}"] < thr for k in fields_short})
    is_complete = ~missing.any(axis=1)

    # --- evidence sources ------------------------------------------------------------------------------------------
    n_links = links.groupby("study_accession").size()
    own_pmids = links.dropna(subset=["pmid"]).groupby("study_accession")["pmid"].apply(
        lambda s: ";".join(sorted({str(x).split(".")[0] for x in s if str(x) not in ("nan", "")})))
    ctrl = controlled_studies(reg, uni, links, ew)
    ew_i = ew.drop_duplicates("study_accession").set_index("study_accession")
    r2_set = set(r2["study_accession"])
    resc = rescue.set_index("study_accession") if len(rescue) else pd.DataFrame()
    si = si.assign(paper_id=si["paper_id"].astype(str))
    si_by_paper = si.groupby("paper_id").agg(n_tables=("member_type", lambda s: int((s == "table").sum())), n_members=("member_type", "size"))
    lp = links.assign(paper_id=links["paper_id"].astype(str)).merge(si_by_paper, left_on="paper_id", right_index=True, how="left")
    si_by_study = lp.groupby("study_accession").agg(n_supp_tables=("n_tables", lambda s: int(np.nansum(s.to_numpy(dtype=float)))),
                                                    n_supp_members=("n_members", lambda s: int(np.nansum(s.to_numpy(dtype=float)))))
    bt = best_tiers(rec)
    hrq_i = hrq.drop_duplicates("study_accession").set_index("study_accession")
    rec_notes = rec.dropna(subset=["note"]).groupby("study_accession")["note"].apply(lambda s: " ".join(map(str, s)))

    # --- per-study blocker ------------------------------------------------------------------------------------------
    order = list(cfg["blocker_order"])
    rows = []
    for acc, u in cand.iterrows():
        if is_complete.loc[acc]:
            continue
        verdict = u["triage_verdict"]
        miss = [k for k in fields_short if missing.loc[acc, k]]
        nl = int(n_links.get(acc, 0))
        ns_t = int(si_by_study["n_supp_tables"].get(acc, 0)) if acc in si_by_study.index else 0
        ns_m = int(si_by_study["n_supp_members"].get(acc, 0)) if acc in si_by_study.index else 0
        access_tier = str(ew_i["access_tier"].get(acc, "")) if acc in ew_i.index else "not_in_extraction_worklist"
        id_form, rescue_status = None, ""
        if len(resc) and acc in resc.index:
            id_form = resc.loc[acc, "id_form"] if isinstance(resc.loc[acc, "id_form"], str) else None
            rescue_status = str(resc.loc[acc, "rescue_status"] or "")
        notes = str(rec_notes.get(acc, ""))
        unit_flag = bool(re.search(r"unit", notes, re.I)) or ("unitless" in rescue_status)
        code, detail = None, ""
        if verdict == "uncertain":
            code = "archive_only_uncertain"
            if acc in hrq_i.index:
                h = hrq_i.loc[acc]
                note = h.get("note")
                detail = f"{h['review_round']}: {note}" if isinstance(note, str) and note else str(h["review_round"])
            else:
                detail = "uncertain verdict; not in human_review_queue"
        else:
            for c in order:
                if c == "controlled_access" and acc in ctrl:
                    code, detail = c, f"controlled access: {ctrl[acc]}"
                elif c == "no_linked_paper" and nl == 0:
                    code, detail = c, f"0 rows in study_paper_links; access_tier={access_tier}"
                elif c == "paywalled_abstract_only" and nl > 0 and re.match(r"^[CDE]_", access_tier):
                    code, detail = c, f"{nl} linked paper(s), access_tier={access_tier}"
                elif c == "tables_unjoinable_need_key" and acc in r2_set:
                    form = pick_id_form(id_form, cfg["default_id_form"])
                    code, detail = c, f"{form}-style sample names (forms seen: {id_form or 'n/a'}); no key to archive accessions" + (f" ({rescue_status})" if rescue_status else "")
                elif c == "pdf_only_supplement" and nl > 0 and ns_m > 0 and ns_t == 0:
                    code, detail = c, f"{ns_m} supplementary member(s) of {nl} paper(s), all PDF/DOCX"
                elif c == "no_supplement_found" and nl > 0 and ns_m == 0:
                    code, detail = c, f"{nl} linked paper(s) ({access_tier}); 0 inventoried supplementary members"
                elif c == "unitless_age_needs_curator" and unit_flag:
                    code, detail = c, f"age column without unit: {rescue_status or notes}"
                elif c == "partial_coverage":
                    code, detail = c, f"{nl} paper(s), {ns_t} inventoried table(s); still missing {', '.join(miss)}"
                if code:
                    break
        ctype = cfg["blocker_to_contribution_type"][code]
        unlock = cfg["unlock_templates"][code].format(id_form=pick_id_form(id_form, cfg["default_id_form"]),
                                                        missing_fields=", ".join(miss) or "the six fields", accession=acc)
        n_cs_i = int(n_cs.loc[acc])
        covs = {k: float(cov.loc[acc, f"coverage_{k}"]) for k in fields_short}
        row = {
            "study_accession": acc, "study_title": u.get("study_title"), "cohort_id": u.get("cohort_id"), "cohort_name": u.get("cohort_name"),
            "triage_verdict": verdict, "n_samples": int(u.get("n_samples") or 0), "n_catalog_scope": n_cs_i,
            "n_infant_samples_est": (None if pd.isna(u.get("n_infant_samples_est")) else float(u.get("n_infant_samples_est"))),
            "missing_fields": ";".join(miss), "n_missing_fields": len(miss),
        }
        for k in fields_short:
            row[f"coverage_{k}"] = round(covs[k], 6)
        for k in fields_short:
            row[f"best_tier_{k}"] = bt["tier"].get((acc, k), "R0") if (acc, k) in bt.index else "R0"
        row.update({
            "blocker_code": code, "blocker_detail": _clip(detail, cfg["tables"]["worklist"]["text_limits"]["blocker_detail"]),
            "unlock_text": _clip(unlock, cfg["tables"]["worklist"]["text_limits"]["unlock_text"]), "contribution_type": ctype,
            "n_linked_papers": nl, "own_data_pmids": own_pmids.get(acc, ""), "n_supp_tables_inventoried": ns_t,
            "controlled_access": acc in ctrl,
            "priority_score": round(priority_score(cfg, {k: row[f"coverage_{k}"] for k in fields_short}, miss, n_cs_i), 6),
            "ena_url": (smw.loc[acc, "ena_url"] if acc in smw.index and isinstance(smw.loc[acc, "ena_url"], str) else cfg["archive_urls"]["ena"].format(accession=acc)),
            "ncbi_url": (smw.loc[acc, "ncbi_url"] if acc in smw.index and isinstance(smw.loc[acc, "ncbi_url"], str) else cfg["archive_urls"]["ncbi"].format(accession=acc)),
            "issue_url": issue_url_for(cfg, acc, ctype, release_id), "release_added": release_id, "release_retired": None, "package_added": package_version,
            "_coverage_scope": cov.loc[acc, "coverage_scope"], "_n_scope": int(cov.loc[acc, "n_scope"]),
        })
        rows.append(row)
    wl = pd.DataFrame(rows)
    wl = wl.sort_values(["priority_score", "n_samples", "study_accession"], ascending=[False, False, True]).reset_index(drop=True)
    wl.insert(0, "rank", np.arange(1, len(wl) + 1))
    scope_info = wl[["study_accession", "_coverage_scope", "_n_scope"]].set_index("study_accession")
    wl = wl[cfg["tables"]["worklist"]["columns"]]

    # --- study × field ------------------------------------------------------------------------------------------------
    frows = []
    lim = cfg["tables"]["fields"]["text_limits"]["evidence"]
    for _, w in wl.iterrows():
        acc = w["study_accession"]
        miss = set(w["missing_fields"].split(";")) if w["missing_fields"] else set()
        for k in fields_short:
            if k not in miss:
                fcode = "complete"
            elif w["blocker_code"] == "unitless_age_needs_curator":
                fcode = "unitless_age_needs_curator" if k == "age" else "partial_coverage"
            else:
                fcode = w["blocker_code"]
            if (acc, k) in bt.index:
                b = bt.loc[(acc, k)]
                ev = _evidence_text(b["evidence"], b["note"], b["tier"])
            else:
                ev = "R0 not assessed by recoverability track"
            frows.append({"study_accession": acc, "field": k, "coverage": float(w[f"coverage_{k}"]), "n_with_value": int(cov.loc[acc, f"n_with_value_{k}"]),
                          "n_catalog_scope": int(w["n_catalog_scope"]), "best_tier": w[f"best_tier_{k}"], "blocker_code": fcode,
                          "evidence": _clip(ev, lim), "release_added": release_id, "release_retired": None, "package_added": package_version})
    fl = pd.DataFrame(frows)[cfg["tables"]["fields"]["columns"]]

    stats = {
        "n_candidates": int(len(cand)), "n_complete": int(is_complete.sum()), "n_open": int(len(wl)),
        "n_open_include": int((wl["triage_verdict"] == "include").sum()), "n_open_uncertain": int((wl["triage_verdict"] == "uncertain").sum()),
        "n_fallback_scope": int((scope_info["_coverage_scope"] == cfg["scopes"]["fallback"]).sum()),
        "blocker_studies": wl["blocker_code"].value_counts().to_dict(),
        "blocker_samples": wl.groupby("blocker_code")["n_samples"].sum().astype(int).to_dict(),
        "blocker_catalog_scope": wl.groupby("blocker_code")["n_catalog_scope"].sum().astype(int).to_dict(),
        "coverage_median": {k: float(wl[f"coverage_{k}"].median()) for k in fields_short},
        "coverage_mean": {k: float(wl[f"coverage_{k}"].mean()) for k in fields_short},
        "n_missing_by_field": {k: int(((fl["field"] == k) & (fl["blocker_code"] != "complete")).sum()) for k in fields_short},
        "contribution_types": wl["contribution_type"].value_counts().to_dict(),
        "n_controlled": int(wl["controlled_access"].sum()), "n_zero_priority": int((wl["priority_score"] == 0).sum()),
        "n_samples_open": int(wl["n_samples"].sum()), "n_catalog_scope_open": int(wl["n_catalog_scope"].sum()),
        "complete_studies": sorted(cand.index[is_complete].tolist()),
        "rescue_rows_parsed": int(len(rescue)), "rescue_id_forms": int(rescue["id_form"].notna().sum()) if len(rescue) else 0,
    }
    return wl, fl, stats


DEVIATIONS = [
    "study_field_coverage_matrix.csv (371 rows) is not on catalog_scope and its scope could not be reproduced from the shipped sample table; "
    "the six coverages were recomputed from sample_metadata_wide on catalog_scope (body-site scope {primary, unknown} for studies with 0 catalog_scope samples).",
    "recoverability.parquet notes never mention 'unit'; the unitless-age signal comes from the RESCUE_REPORT_v2 status text only "
    "and is masked by tables_unjoinable_need_key for the study that carries it (frozen decision order).",
    "controlled_access is derived from the registry via study accession, cohort_id and linked paper_ids (the registry is keyed by dbGaP/EGA/GSA accessions, not BioProjects); "
    "the source of each match is in blocker_detail.",
]


def write_report(wl: pd.DataFrame, stats: dict, out: str, cfg: dict, release_id: str, package_version: str, deviations: list[str]) -> None:
    fs = list(cfg["field_order"])
    L = [f"# Contribute worklist — {release_id} (package {package_version})", "",
         f"Open studies: **{stats['n_open']}** ({stats['n_open_include']} include + {stats['n_open_uncertain']} uncertain) out of "
         f"{stats['n_candidates']} include/uncertain studies; {stats['n_complete']} complete (all six fields ≥ {cfg['missing_threshold']} coverage) and therefore not listed. "
         f"Open studies hold {stats['n_samples_open']:,} samples ({stats['n_catalog_scope_open']:,} catalog_scope).",
         f"Coverage scope: catalog_scope for {stats['n_open'] - stats['n_fallback_scope']} studies; body-site-scope fallback for {stats['n_fallback_scope']} studies with 0 catalog_scope samples "
         f"(their priority_score is 0 by the frozen formula log10(n_catalog_scope+1); they are ranked after all scored studies by n_samples).", "",
         "## Blocker distribution", "", "| blocker_code | studies | samples | catalog_scope samples |", "|---|---|---|---|"]
    for c, n in sorted(stats["blocker_studies"].items(), key=lambda x: -x[1]):
        L.append(f"| `{c}` | {n} | {stats['blocker_samples'].get(c, 0):,} | {stats['blocker_catalog_scope'].get(c, 0):,} |")
    L += ["", "| contribution_type (primary ask) | studies |", "|---|---|"]
    for c, n in sorted(stats["contribution_types"].items(), key=lambda x: -x[1]):
        L.append(f"| `{c}` | {n} |")
    L += ["", f"Controlled-access studies: {stats['n_controlled']}. Studies with priority_score 0: {stats['n_zero_priority']}.", "",
          "## Per-field coverage over open studies", "", "| field | median coverage | mean coverage | studies missing (< threshold) |", "|---|---|---|---|"]
    for k in fs:
        L.append(f"| {k} | {stats['coverage_median'][k]:.3f} | {stats['coverage_mean'][k]:.3f} | {stats['n_missing_by_field'][k]} |")
    L += ["", "## Top 25", "", "| rank | study | verdict | n_samples | n_catalog_scope | missing | blocker | ask | priority |", "|---|---|---|---|---|---|---|---|---|"]
    for _, r in wl.head(25).iterrows():
        L.append(f"| {r['rank']} | {r['study_accession']} | {r['triage_verdict']} | {r['n_samples']:,} | {r['n_catalog_scope']:,} | {r['missing_fields']} | `{r['blocker_code']}` | `{r['contribution_type']}` | {r['priority_score']:.2f} |")
    L += ["", "## Inputs parsed", "", f"* RESCUE_REPORT_v2.md: {stats['rescue_rows_parsed']} per-study rows, {stats['rescue_id_forms']} with a sample-ID form.",
          f"* Complete studies (not listed): {len(stats['complete_studies'])} — {', '.join(stats['complete_studies'][:40])}{'…' if len(stats['complete_studies']) > 40 else ''}", "",
          "## Deviations", ""]
    L += [f"* {d}" for d in deviations] or ["* none"]
    open(out, "w", encoding="utf-8").write("\n".join(L) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--package", required=True, help="unpacked package dir (input tables)")
    ap.add_argument("--inputs", required=True, help="dir with the artifact inputs (config/inputs.json group contribute)")
    ap.add_argument("--out", required=True, help="output dir (normally = --package so the files enter the release)")
    ap.add_argument("--release-id", required=True)
    ap.add_argument("--package-version", required=True)
    ap.add_argument("--report", default=None, help="WORKLIST_REPORT.md path (default: <out>/../WORKLIST_REPORT.md)")
    ap.add_argument("--config", default=None)
    a = ap.parse_args(argv)
    cfg = load_config(a.config)
    for f in INPUT_FILES.values():
        assert os.path.exists(os.path.join(a.inputs, f)), f"missing input {f} under {a.inputs} (bootstrap.py materialises group `contribute`)"
    wl, fl, stats = build(a.package, a.inputs, cfg, a.release_id, a.package_version)
    os.makedirs(a.out, exist_ok=True)
    wl.to_csv(os.path.join(a.out, cfg["tables"]["worklist"]["file"]), index=False)
    fl.to_csv(os.path.join(a.out, cfg["tables"]["fields"]["file"]), index=False)
    rep = a.report or os.path.join(os.path.dirname(os.path.abspath(a.out.rstrip("/"))), "WORKLIST_REPORT.md")
    write_report(wl, stats, rep, cfg, a.release_id, a.package_version, DEVIATIONS)
    json.dump(stats, open(os.path.join(os.path.dirname(rep), "worklist_stats.json"), "w"), indent=1, sort_keys=True)
    print(json.dumps({k: stats[k] for k in ("n_candidates", "n_complete", "n_open", "n_open_include", "n_open_uncertain", "n_fallback_scope", "blocker_studies")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

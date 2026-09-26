"""Deterministic subject and timepoint resolution for the infant gut shotgun-metagenome catalog.

No LLM. Inputs: sample_determinations.parquet, samples.parquet, sample_attributes.parquet,
sample_id_conventions.csv, cohorts_v3.csv. Outputs: sample_subjects.parquet, subjects.parquet,
study_subject_summary.csv, cohorts_v4.csv.

Subject-id precedence (per sample, first non-empty wins):
  1. determinations field subject_id, route R1 then R2 (highest confidence within route)
  2. sample attributes with subject-like keys (ordered key list below); family-type keys only
     when combined with a role attribute
  3. samples.subject_id_raw
  4. sample-name conventions: r1_title_parser.parse_sample_name subject ordinal, then the
     residual of the sample title after removing the study's timepoint token
     (sample_id_conventions.csv regex)
Role: mother if body_site_class=='linked', a role attribute says mother, or the title/library
name carries a maternal token; father/sibling/educator/pet -> other; infant when the sample is a
primary/excluded-site infant sample or a life-stage attribute says infant/neonate/child.
Mothers link to an infant subject of the same study when the id cores agree after stripping
role tokens, or when a family/dyad attribute is shared.
Timepoints: age_at_collection_days (sample scope, R1>R2>R3>R4) > collection_date (full ISO date)
> numeric token of timepoint_label; distinct values per subject are ranked -> t_index.
"""
# --- catalog-pipeline repo layout shim (added 2026-09-26; original ran flat from one cwd) ---
import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__)) if "__file__" in globals() else _os.getcwd()
for _p in (_here, _os.path.join(_here, "..", "..")):
    _p = _os.path.abspath(_p)
    if _p not in _sys.path:
        _sys.path.insert(0, _p)
try:
    from catalog.models import resolve_model, set_host  # registers src/catalog/<stage>/ dirs on sys.path
except ImportError:  # flat-workspace mode (files copied side by side): models.py must sit alongside
    from models import resolve_model, set_host
set_host(globals().get("host"))  # kernel `host` is a frame global, not builtins (R1-01)
def _prompt_path(name):
    """cwd copy first (leaf-worker convention), else the packaged prompt under src/catalog/prompts/."""
    for _c in (name, _os.path.join("pilot_prompts", name), _os.path.join(_here, "..", "prompts", name)):
        if _os.path.exists(_c):
            return _c
    return name
# ---------------------------------------------------------------------------------------------
import re, sys, os, json
import numpy as np
import pandas as pd

# (sys.path handled by the repo layout shim above)
from r1_title_parser import parse_sample_name

ROUTE_RANK = {"R1": 0, "R2": 1, "R3": 2, "R4": 3}
SUBJECT_KEYS = ["host_subject_id", "subject_id", "submitted_subject_id", "gap_subject_id", "subjectid", "subject",
                "host_subject", "individual_id", "individual", "participant_id", "participant", "infant_id",
                "babyid", "baby_id", "child_id", "patient_id", "patient", "patient_code", "personcode",
                "subject_number", "host_id", "donor_id", "donor", "volunteer_id", "proband_id"]
FAMILY_KEYS = ["dyad_id", "family_id", "host_family_id", "family_number", "host_family", "family", "pair_id", "twin_pair"]
ROLE_KEYS = ["host_family_relationship", "motherorbaby_m_b", "participant_type", "family_relationship", "source",
             "host_life_stage", "sample_type", "subject_type", "host_type", "relationship", "mother_or_infant",
             "individual_type", "family_member", "role", "host_description"]
BAD_ID = {"", "na", "n/a", "nan", "none", "null", "missing", "not applicable", "not collected", "not provided",
          "unknown", "-", "?", "missing: not provided", "not available", "restricted access"}
RX_MOTHER = re.compile(r"(?<![A-Za-z])(mother|maternal|mom|mum|gest|gestation|prenatal|pregnan|trimester|breast ?milk|vagin|placent|colostrum|cervic)", re.I)
RX_INFANT = re.compile(r"(?<![A-Za-z])(infant|baby|babies|neonat|newborn|child|kid|offspring|toddler)", re.I)
RX_OTHER = re.compile(r"(?<![A-Za-z])(father|dad|paternal|sibling|educator|pet|dog|cat|grandm|husband|wife|adult)", re.I)
RX_STRIP_ROLE = re.compile(r"(mother|maternal|mom|mum|infant|baby|child|kid|neonate|newborn)", re.I)
SRC_CONF = {"det_subject_id_R1": 0.9, "det_subject_id_R2": 0.85, "attr_subject_key": 0.85, "attr_family_key+role": 0.75,
            "subject_id_raw": 0.7, "name_parser_ordinal": 0.55, "name_convention_residual": 0.45}


def clean_id(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    s = str(v).strip()
    if s.lower() in BAD_ID or len(s) == 0:
        return None
    return s


def id_core(s):
    """Strip role words and single M/B/I role letters at token boundaries; keep alnum core."""
    s = RX_STRIP_ROLE.sub("", str(s))
    s = re.sub(r"(?<![A-Za-z0-9])[MBI](?=[-_ .]|\d|$)", "", s)   # M12, B12, M_12, 12 handled below
    s = re.sub(r"(?<=\d)[MBI](?![A-Za-z0-9])", "", s)             # 12M, 12B
    s = re.sub(r"[^A-Za-z0-9]+", "", s).lower()
    return s or None


def parse_date(s):
    if s is None or not isinstance(s, str):
        return None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s.strip())
    if not m:
        return None
    try:
        return pd.Timestamp(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except Exception:
        return None


def tp_numeric(label):
    if not isinstance(label, str):
        return None
    p = parse_sample_name(label)
    if p["age_days"] is not None:
        return float(p["age_days"])
    m = re.search(r"(\d{1,3}(?:\.\d+)?)", label)
    return float(m.group(1)) if m else None


def resolve(det, sam, att, conv, coh, outdir="."):
    sam = sam.copy()
    # ---- 1. determinations: subject_id
    sd = det[det.field_name == "subject_id"].copy()
    sd["rr"] = sd.route.map(ROUTE_RANK)
    sd = sd.sort_values(["sample_key", "rr", "confidence"], ascending=[True, True, False]).drop_duplicates("sample_key")
    sd["v"] = sd.value_normalized.map(clean_id)
    sd = sd[sd.v.notna()]
    det_id = dict(zip(sd.sample_key, sd.v)); det_src = dict(zip(sd.sample_key, "det_subject_id_" + sd.route))
    # ---- 2. attributes
    a = att[att.attr_key_norm.isin(SUBJECT_KEYS + FAMILY_KEYS + ROLE_KEYS)][["sample_key", "attr_key_norm", "attr_value"]]
    a["attr_value"] = a.attr_value.map(clean_id)
    a = a[a.attr_value.notna()]
    key_rank = {k: i for i, k in enumerate(SUBJECT_KEYS)}
    sa = a[a.attr_key_norm.isin(SUBJECT_KEYS)].copy()
    sa["kr"] = sa.attr_key_norm.map(key_rank)
    sa = sa.sort_values(["sample_key", "kr"]).drop_duplicates("sample_key")
    attr_id = dict(zip(sa.sample_key, sa.attr_value)); attr_key = dict(zip(sa.sample_key, sa.attr_key_norm))
    fam_rank = {k: i for i, k in enumerate(FAMILY_KEYS)}
    fa = a[a.attr_key_norm.isin(FAMILY_KEYS)].copy()
    fa["kr"] = fa.attr_key_norm.map(fam_rank)
    fa = fa.sort_values(["sample_key", "kr"]).drop_duplicates("sample_key")
    fam_id = dict(zip(fa.sample_key, fa.attr_value))
    ra = a[a.attr_key_norm.isin(ROLE_KEYS)]
    role_text = ra.groupby("sample_key").apply(lambda g: " | ".join(f"{k}={v}" for k, v in zip(g.attr_key_norm, g.attr_value))).to_dict()
    # ---- age / timepoint determinations
    ag = det[(det.field_name == "age_at_collection_days") & (det.scope == "sample")].copy()
    ag["rr"] = ag.route.map(ROUTE_RANK)
    ag["age"] = pd.to_numeric(ag.value_normalized, errors="coerce")
    ag = ag[ag.age.notna()].sort_values(["sample_key", "rr", "confidence"], ascending=[True, True, False]).drop_duplicates("sample_key")
    age_map = dict(zip(ag.sample_key, ag.age)); age_src = dict(zip(ag.sample_key, ag.route))
    tl = det[det.field_name == "timepoint_label"].copy()
    tl["rr"] = tl.route.map(ROUTE_RANK)
    tl = tl.sort_values(["sample_key", "rr", "confidence"], ascending=[True, True, False]).drop_duplicates("sample_key")
    tp_map = dict(zip(tl.sample_key, tl.value_normalized))
    # ---- conventions: per-study timepoint regex for residual stripping
    conv_rx = {}
    for st, g in conv.groupby("study_accession"):
        rxs = []
        for r in g.regex.dropna().unique():
            try:
                rxs.append(re.compile(r))
            except re.error:
                pass
        conv_rx[st] = rxs

    rows = []
    for r in sam.itertuples(index=False):
        sk = r.sample_key
        title = r.sample_title if isinstance(r.sample_title, str) else ""
        lib = r.library_name if isinstance(r.library_name, str) else ""
        pt = parse_sample_name(title); pl = parse_sample_name(lib)
        # --- subject id
        sid = src = None
        if sk in det_id:
            sid, src = det_id[sk], det_src[sk]
        elif sk in attr_id:
            sid, src = attr_id[sk], "attr_subject_key"
        rtxt = role_text.get(sk, "")
        if sid is None and sk in fam_id and rtxt:
            sid, src = fam_id[sk], "attr_family_key+role"
        if sid is None and isinstance(r.subject_id_raw, str) and clean_id(r.subject_id_raw):
            sid, src = r.subject_id_raw.strip(), "subject_id_raw"
        if sid is None:
            o = pt["subject_id"] or pl["subject_id"]
            if o:
                sid, src = o, "name_parser_ordinal"
        if sid is None and r.study_accession in conv_rx and title:
            for rx in conv_rx[r.study_accession]:
                m = rx.search(title)
                if m and m.start() > 0:
                    resid = re.sub(r"[-_ .:/]+$", "", title[:m.start()]).strip()
                    if len(resid) >= 2 and resid != title and len(resid.split()) <= 2 and re.search(r"\d", resid):
                        sid, src = resid, "name_convention_residual"
                        break
        # --- role
        role, role_src = None, None
        txt_all = f"{title} {lib} {r.body_site_raw or ''} {rtxt}"
        if r.body_site_class == "linked":
            role, role_src = "mother", "body_site_class=linked"
        elif rtxt and re.search(r"(motherorbaby_m_b=M\b|=\s*(mother|mom|maternal)\b)", rtxt, re.I):
            role, role_src = "mother", "attr_role"
        elif pt["is_mother"] or pl["is_mother"]:
            role, role_src = "mother", "sample_name_token"
        elif RX_MOTHER.search(str(r.body_site_raw or "")):
            role, role_src = "mother", "body_site_raw"
        elif rtxt and re.search(r"=\s*(father|dad|sibling|educator|pet|adult|husband|wife|grand)", rtxt, re.I):
            role, role_src = "other", "attr_role"
        elif rtxt and re.search(r"(motherorbaby_m_b=B\b|=\s*(infant|baby|neonate|newborn|child)\b)", rtxt, re.I):
            role, role_src = "infant", "attr_role"
        elif RX_OTHER.search(f"{title} {lib}"):
            role, role_src = "other", "sample_name_token"
        elif r.body_site_class in ("primary", "excluded"):
            role, role_src = "infant", "body_site_class"
        elif RX_INFANT.search(txt_all):
            role, role_src = "infant", "sample_name_token"
        else:
            role, role_src = "unknown", None
        # --- age / timepoint / date
        age = age_map.get(sk)
        d = parse_date(r.collection_date)
        tpl = tp_map.get(sk)
        if tpl is None and (pt["timepoint_label"] or pl["timepoint_label"]):
            tpl = pt["timepoint_label"] or pl["timepoint_label"]
        rows.append(dict(sample_key=sk, study_accession=r.study_accession, subject_id_resolved=sid, subject_source=src,
                         role=role, role_source=role_src, family_id=fam_id.get(sk), age_days_used=age,
                         age_source=age_src.get(sk), collection_dt=d, timepoint_label=tpl, tp_num=tp_numeric(tpl),
                         body_site_class=r.body_site_class))
    ss = pd.DataFrame(rows)
    # ---- degenerate-id guard: an id shared by >200 samples or >50% of a study with >40 samples is a constant, not a subject
    cnt = ss.groupby(["study_accession", "subject_id_resolved"]).sample_key.transform("size")
    stn = ss.groupby("study_accession").sample_key.transform("size")
    nuniq = ss.groupby("study_accession").subject_id_resolved.transform("nunique")
    short = ss.subject_id_resolved.fillna("").str.len() <= 1
    degen = ss.subject_id_resolved.notna() & ((cnt > 200) | ((stn > 40) & (cnt > 0.5 * stn))
                                              | ((stn > 50) & (nuniq <= 5) & (cnt > 20)) | short)
    ss.loc[degen, "subject_source"] = "rejected_degenerate:" + ss.loc[degen, "subject_source"].astype(str)
    ss.loc[degen, "subject_id_resolved"] = None
    # ---- subject keys; mothers sharing an id string with an infant get a suffix
    ss["subject_key"] = None
    has = ss.subject_id_resolved.notna()
    inf_ids = set(zip(ss.loc[has & (ss.role != "mother"), "study_accession"], ss.loc[has & (ss.role != "mother"), "subject_id_resolved"]))
    def mk(r):
        if pd.isna(r.subject_id_resolved):
            return None
        sid = r.subject_id_resolved
        if r.role == "mother" and (r.study_accession, sid) in inf_ids:
            sid = sid + "_mother"
        return f"{r.study_accession}|{sid}"
    ss["subject_key"] = ss.apply(mk, axis=1)
    # ---- mother -> infant link
    ss["core"] = ss.subject_id_resolved.map(lambda x: id_core(x) if isinstance(x, str) else None)
    inf = ss[(ss.role == "infant") & ss.subject_key.notna()]
    core_map = inf.groupby(["study_accession", "core"]).subject_key.agg(lambda x: sorted(set(x))).to_dict()
    fam_map = inf[inf.family_id.notna()].groupby(["study_accession", "family_id"]).subject_key.agg(lambda x: sorted(set(x))).to_dict()
    def link(r):
        if r.role != "mother":
            return None
        c = fam_map.get((r.study_accession, r.family_id)) if r.family_id else None
        if not c and r.core:
            c = core_map.get((r.study_accession, r.core))
        if c and len(c) <= 3:   # a mother of 1-3 infants (twins/triplets)
            return "|".join(c)
        return None
    ss["linked_infant_subject_key"] = ss.apply(link, axis=1)
    # ---- timepoints per subject
    ss["t_index"] = np.nan; ss["n_timepoints_subject"] = np.nan; ss["t_basis"] = None
    grp_key = ss.subject_key.where(ss.subject_key.notna(), "SINGLE::" + ss.sample_key)
    for key, idx in ss.groupby(grp_key).indices.items():
        g = ss.iloc[idx]
        n = len(g)
        if n == 1:
            ss.loc[g.index, ["t_index", "n_timepoints_subject", "t_basis"]] = [1, 1, "single_sample"]
            continue
        for col, basis in (("age_days_used", "age_days"), ("collection_dt", "collection_date"), ("tp_num", "timepoint_label")):
            vals = g[col]
            if vals.notna().sum() >= max(2, int(0.5 * n)):
                ranks = vals.rank(method="dense")
                ss.loc[g.index, "t_index"] = ranks.values
                ss.loc[g.index, "n_timepoints_subject"] = int(vals.dropna().nunique())
                ss.loc[g.index, "t_basis"] = basis
                break
        else:
            ss.loc[g.index, "n_timepoints_subject"] = 1 if n == 1 else np.nan
            ss.loc[g.index, "t_basis"] = "unordered"
    out = ss[["sample_key", "study_accession", "subject_key", "subject_id_resolved", "role", "role_source", "subject_source",
              "linked_infant_subject_key", "t_index", "n_timepoints_subject", "t_basis", "age_days_used", "age_source",
              "timepoint_label"]].copy()
    out.to_parquet(os.path.join(outdir, "sample_subjects.parquet"), index=False)
    # ---- subjects table
    sub = (ss[ss.subject_key.notna()].groupby("subject_key")
           .agg(study_accession=("study_accession", "first"), subject_id_resolved=("subject_id_resolved", "first"),
                role=("role", lambda x: x.value_counts().index[0]), n_samples=("sample_key", "size"),
                n_timepoints=("n_timepoints_subject", "max"), subject_source=("subject_source", "first"),
                linked_infant_subject_key=("linked_infant_subject_key", lambda x: next((v for v in x if v), None)),
                age_min_days=("age_days_used", "min"), age_max_days=("age_days_used", "max")).reset_index())
    sub.to_parquet(os.path.join(outdir, "subjects.parquet"), index=False)
    # ---- study summary
    summ = []
    for st, g in ss.groupby("study_accession"):
        gi = g[g.role == "infant"]
        res = gi.subject_key.notna()
        n_inf_subj = gi.loc[res, "subject_key"].nunique()
        n_unres = int((~res).sum())
        n_est = n_inf_subj + n_unres if res.any() else np.nan
        per = gi[res].groupby("subject_key").size()
        ntp = gi[res].groupby("subject_key").n_timepoints_subject.max()
        frac_long = float((ntp >= 2).mean()) if len(ntp) else 0.0
        srcs = g.subject_source.dropna(); srcs = srcs[~srcs.str.startswith("rejected")]
        dom = srcs.value_counts().index[0] if len(srcs) else "unresolved"
        cov = float(res.mean()) if len(gi) else 0.0
        conf = round(SRC_CONF.get(dom, 0.3) * cov, 2) if len(srcs) else 0.0
        summ.append(dict(study=st, n_samples=len(g), n_infant_samples=len(gi), n_infant_samples_resolved=int(res.sum()),
                         n_unique_infants_est=n_est, n_mothers=g.loc[g.role == "mother", "subject_key"].nunique(),
                         n_mother_samples=int((g.role == "mother").sum()), n_other_samples=int((g.role == "other").sum()),
                         longitudinal=bool(len(ntp) and (frac_long >= 0.1 or ntp.max() >= 3)),
                         frac_infants_longitudinal=round(frac_long, 3), max_timepoints=float(ntp.max()) if len(ntp) else np.nan,
                         median_samples_per_infant=float(per.median()) if len(per) else np.nan,
                         resolution_source=dom, subject_coverage=round(cov, 3), confidence=conf,
                         n_mothers_linked=int(g[(g.role == "mother")].linked_infant_subject_key.notna().sum())))
    summ = pd.DataFrame(summ).sort_values("study")
    summ.to_csv(os.path.join(outdir, "study_subject_summary.csv"), index=False)
    # ---- cohorts v4
    est = summ.set_index("study").n_unique_infants_est.to_dict()
    c4 = coh.copy()
    c4["unique_infants_est_prev"] = c4.unique_infants_est
    new, src = [], []
    for accs in c4.study_accessions.fillna("").astype(str):
        members = [x for x in accs.split("|") if x]
        vals = [est.get(m) for m in members]
        known = [v for v in vals if v is not None and not (isinstance(v, float) and np.isnan(v))]
        if members and len(known) == len(members):
            new.append(float(sum(known))); src.append("subject_resolution:all_members")
        elif known:
            new.append(float(sum(known))); src.append(f"subject_resolution:{len(known)}/{len(members)}_members")
        else:
            new.append(np.nan); src.append("unresolved")
    new = pd.Series(new, index=c4.index); src = pd.Series(src, index=c4.index)
    full = src == "subject_resolution:all_members"
    c4["unique_infants_est"] = new.where(full, c4.unique_infants_est)          # override only when every member study resolved
    c4["unique_infants_est_partial"] = new.where(~full & (src != "unresolved"))  # partial sums reported, never override
    c4["unique_infants_est_source"] = src.where(full, "cohorts_v3:" + src)
    c4.to_csv(os.path.join(outdir, "cohorts_v4.csv"), index=False)
    return out, sub, summ, c4


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    for k in ("det", "sam", "att", "conv", "coh"):
        p.add_argument("--" + k, required=True)
    a = p.parse_args()
    resolve(pd.read_parquet(a.det), pd.read_parquet(a.sam), pd.read_parquet(a.att), pd.read_csv(a.conv), pd.read_csv(a.coh))

"""Read-only lookup helpers for the AUDITOR role. Expects a dict T of loaded DataFrames."""
# --- microbiome_repo-pipeline repo layout shim (added 2026-09-26; original ran flat from one cwd) ---
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
import re, json, datetime
import pandas as pd

FIELDS = ["age_at_collection_days","preterm_status","gestational_age_weeks","delivery_mode","feeding_mode",
          "antibiotic_exposure","probiotic_exposure","birth_weight_grams","country","maternal_antibiotics",
          "hmo_supplementation","nec_status","health_condition","multiple_birth","sibling_in_study",
          "geo_subregion","sex","timepoint_label","subject_id"]
FIND_COLS = ["date","identifier","finding_type","current_state","proposed_change","evidence_quote","evidence_source","confidence"]

def _ev(s):
    if s is None or (isinstance(s,float) and pd.isna(s)): return []
    if isinstance(s,(list,tuple)): return list(s)
    try: return json.loads(s)
    except Exception: return [{"source":"?","quote":str(s)}]

def ev_str(s):
    return " | ".join(f'{e.get("source")}: "{e.get("quote")}"' for e in _ev(s)) or "—"

def kind_of(ident):
    i = ident.strip()
    if re.fullmatch(r"PRJ[A-Z]{2}\d+", i): return "study"
    if re.fullmatch(r"(SAM[NED][A-Z]?\d+|[SED]RS\d+)", i): return "sample"
    if re.fullmatch(r"[SED]RR\d+", i): return "run"
    if re.fullmatch(r"[SED]RX\d+", i): return "experiment"
    if re.fullmatch(r"[SED]RP\d+", i): return "secondary_study"
    if re.fullmatch(r"COH\d+", i): return "cohort"
    if re.fullmatch(r"PMC\d+", i, re.I): return "pmcid"
    if re.fullmatch(r"\d{6,9}", i): return "pmid"
    if re.match(r"10\.\d{4,9}/", i): return "doi"
    return "text"

# ---------------- study level ----------------
def study_row(T, acc):
    S = T["studies"]; r = S[S.study_accession == acc]
    return None if r.empty else r.iloc[0]

def secondary_to_primary(T, sec):
    u = T["univ_runs"]; hit = u.loc[u.secondary_study_accession == sec, "study_accession"]
    if hit.empty:
        us = T["univ_studies"]; hit = us.loc[us.secondary_study_accession == sec, "study_accession"]
    return None if hit.empty else hit.iloc[0]

def universe_block(T, acc):
    r = study_row(T, acc)
    out = {"in_catalog_studies": r is not None}
    if r is not None:
        out.update(universe_slice=r.universe_slice, catalog_status=r.catalog_status,
                   n_samples=r.n_samples, n_runs=r.n_runs, first_public=r.first_public_min,
                   sig_infant_hit=r.sig_infant_hit, screen_haiku=r.screen_haiku, linked_infant_paper=r.linked_infant_paper,
                   controlled_access=r.controlled_access, study_title=r.study_title)
    us = T["univ_studies"]; ur = us[us.study_accession == acc]
    out["in_universe_v3_full"] = not ur.empty
    if not ur.empty:
        x = ur.iloc[0]
        out.update(v3_channels=x.enumeration_channels, v3_tags=x.enumeration_tags, v3_n_runs=x.n_runs, v3_n_samples=x.n_samples,
                   v3_library_strategies=x.library_strategies, v3_library_sources=x.library_sources,
                   v3_tax=x.scientific_names, v3_host_tax_ids=x.host_tax_ids, v3_adjudication_only=x.adjudication_only)
    ff = T["frame_free"]; fr = ff[ff.study_accession == acc]
    if not fr.empty:
        f = fr.iloc[0]
        out.update(frame_free_human_signal=f.human_signal, frame_free_reason=f.human_signal_reason, frame_free_rule=f.signal_rule,
                   frame_free_n_runs=f.n_runs, frame_free_tax_ids=f.tax_ids)
    runs = T["univ_runs"][T["univ_runs"].study_accession == acc]
    out["archive_runs_v3"] = len(runs); out["archive_samples_v3"] = runs.sample_accession.nunique()
    if len(runs):
        out["archive_strategy_source"] = runs.groupby(["library_strategy","library_source"]).size().to_dict()
    return out

def triage_block(T, acc):
    r = study_row(T, acc); out = {}
    if r is not None:
        out["final"] = dict(verdict=r.triage_verdict, catalog_status=r.catalog_status, outcome=r.outcome, stage=r.decision_stage,
                            model=r.model, confidence=r.confidence, reason_code=r.reason_code, evidence=ev_str(r.evidence),
                            note=r.note, n_infant_samples_est=r.n_infant_samples_est, body_site_call=r.body_site_call,
                            validator_ok=r.validator_ok, validator_msg=r.validator_msg)
    tr = T["triage"][T["triage"].record_id == acc]
    out["triage_v2_rows"] = [dict(value=x.value, outcome=x.outcome, stage=x.stage, model=x.model, confidence=x.confidence,
                                  reason_code=x.reason_code, evidence=ev_str(x.evidence), note=x.note) for _, x in tr.iterrows()]
    revs = []
    for k in ["hr1","hr2"]:
        h = T[k][T[k].study_accession == acc]
        for _, x in h.iterrows():
            revs.append(dict(round=k, stage=x.stage, value=x.value, outcome=x.outcome, confidence=x.confidence, reason_code=x.reason_code,
                             evidence=ev_str(x.evidence), sources_used=x.evidence_sources_used, note=x.note,
                             evidence_limited_to=x.evidence_limited_to, n_infant_samples_est=x.n_infant_samples_est, model=x.model))
    out["review_rounds"] = revs
    q = T["hrq"][T["hrq"].study_accession == acc]
    out["in_human_review_queue"] = None if q.empty else dict(review_round=q.iloc[0].review_round, note=q.iloc[0].note, verdict=q.iloc[0].triage_verdict)
    g = T["gold"][T["gold"].study_accessions.fillna("").str.contains(acc)]
    out["gold"] = None if g.empty else g[["study_name","gold_role","truth","reason_code","n_infant_samples","n_total_samples","note"]].to_dict("records")
    rel = T["relations"][(T["relations"].source_study == acc) | (T["relations"].related_study == acc)]
    out["relations"] = rel[["source_study","related_study","relation_type","evidence","related_in_catalog"]].to_dict("records")
    return out

def _pmid_str(v):
    if v is None or (isinstance(v,float) and pd.isna(v)): return None
    s = str(v);  return s[:-2] if s.endswith(".0") else s

def papers_block(T, acc):
    rows = []
    for k in ["psl","psl_new","psl_new2"]:
        d = T[k][T[k].study_accession == acc]
        for _, x in d.iterrows():
            rows.append(dict(table=k, paper_id=x.paper_id, pmid=_pmid_str(x.pmid), pmcid=x.pmcid, relation=x.relation, method=x.method,
                             confidence=x.confidence, contested=x.contested, sections=x.sections, evidence=ev_str(x.evidence),
                             title=x.get("title", None)))
    spl = T["spl"][T["spl"].study_accession == acc]
    for _, x in spl.iterrows():
        rows.append(dict(table="spl", paper_id=x.paper_id, pmid=_pmid_str(x.pmid), pmcid=x.pmcid, relation=None, method=None, title=x.title))
    sb = T["snowball"][T["snowball"].study_accession == acc]
    snow = sb[["paper_id","pmid","accession_type","accession","source"]].to_dict("records")
    df = pd.DataFrame(rows)
    if not df.empty:
        # attach titles/access tier from papers_raw
        P = T["papers"].set_index("id"); A = T["access"].set_index("id")
        def title(pid):
            pid = str(pid)
            return P.title.get(pid) if pid in P.index else None
        def tier(pid):
            pid = str(pid); return A.access_tier.get(pid) if pid in A.index else None
        df["title"] = [t if isinstance(t,str) else title(p) for t,p in zip(df.title, df.paper_id)]
        df["access_tier"] = [tier(p) for p in df.paper_id]
    return df, snow

def samples_block(T, acc):
    smw = T["smw"][T["smw"].study_accession == acc]
    sm = T["samples"][T["samples"].study_accession == acc]
    inc = T["inc_runs"][T["inc_runs"].study_accession == acc]
    out = dict(catalog_samples=len(sm), catalog_runs=len(inc),
               body_site_class=sm.body_site_class.value_counts().to_dict() if len(sm) else {},
               role=smw.role.value_counts(dropna=False).to_dict() if len(smw) else {},
               adult_age_flag=int(smw.adult_age_flag.fillna(False).astype(bool).sum()) if len(smw) else 0)
    cov = []
    n = len(smw)
    for f in FIELDS:
        if f not in smw.columns: continue
        has = smw[f].notna(); k = int(has.sum())
        routes = smw.loc[has, f + "__route"].value_counts().to_dict() if k else {}
        cov.append(dict(field=f, n=k, pct=round(100*k/n,1) if n else None, routes=routes))
    out["coverage"] = pd.DataFrame(cov)
    return out, smw

def gaps_block(T, acc):
    out = {}
    r1 = T["r1rej"][T["r1rej"].study_accession == acc]
    out["r1_rejected"] = r1.groupby(["field_name","reject_reason"]).size().sort_values(ascending=False).head(15).reset_index(name="n")
    dr = T["sdet_drop"][T["sdet_drop"].study_accession == acc]
    out["dropped_group"] = dr.groupby(["field_name","value_normalized","evidence_quote","drop_reason"]).size().reset_index(name="n")
    ga = T["gaudit"][T["gaudit"].study_accession == acc]
    out["group_audit"] = ga[["field_name","value_normalized","evidence_source","evidence_quote","route","n_samples","verdict","audit_reason","failure_mode"]]
    ad = T["adult"][T["adult"].study_accession == acc]
    out["adult_age_rows"] = dict(n=len(ad), fields=ad.field_name.value_counts().to_dict(),
                                 examples=ad[["sample_key","field_value","unit","age_days","evidence_source","evidence_quote"]].head(5).to_dict("records"))
    rj = T["sdet_rej"][T["sdet_rej"].study_accession == acc]
    out["validator_rejected"] = rj
    r = study_row(T, acc)
    if r is not None:
        out["recov_tiers"] = {c: r[c] for c in ["recov_age","recov_antibiotics","recov_delivery","recov_feeding","recov_preterm","recov_probiotic"]}
        out["worklist_rank"] = r.worklist_rank; out["effort_class"] = r.effort_class
    si = T["supp_inv"]
    if "study_accession" in si.columns:
        out["supp_tables"] = si[si.study_accession == acc]
    return out

def rescue_report_lines(acc, files=("RESCUE_REPORT_v2.md","R2_FULL_V2_REPORT.md")):
    hits = []
    for f in files:
        try:
            for i, line in enumerate(open(f, encoding="utf-8")):
                if acc in line: hits.append((f, i+1, line.rstrip()[:400]))
        except FileNotFoundError: pass
    return hits

def cohort_block(T, acc):
    c = T["cohorts"]; hit = c[c.study_accessions.fillna("").str.contains(acc)]
    return hit[["cohort_id","cohort_name","n_studies","study_accessions","paper_ids","n_samples_total","unique_infants_est","included_study_accessions"]].to_dict("records")

# ---------------- sample / run level ----------------
def locate_sample(T, ident):
    """Return (study_accession, sample_key, matched_via)."""
    sm = T["samples"]
    for col in ["sample_key","secondary_sample"]:
        h = sm[sm[col] == ident]
        if not h.empty: return h.iloc[0].study_accession, h.iloc[0].sample_key, f"samples.{col}"
    ir = T["inc_runs"]
    for col in ["run_accession","experiment_accession","sample_accession","secondary_sample_accession"]:
        h = ir[ir[col] == ident]
        if not h.empty:
            x = h.iloc[0]; return x.study_accession, x.sample_accession, f"catalog_included_runs.{col}"
    ur = T["univ_runs"]
    for col in ["run_accession","experiment_accession","sample_accession","secondary_sample_accession"]:
        h = ur[ur[col] == ident]
        if not h.empty:
            x = h.iloc[0]; return x.study_accession, x.sample_accession, f"universe_v3_full_runs.{col} (not in catalog samples)"
    return None, None, None

def sample_evidence(T, sample_key):
    cols = ["field_name","field_value","value_normalized","confidence","route","scope","evidence_source","evidence_locator","evidence_quote","determined_by","parse_note","group_audit","evidence_limited_to_abstract"]
    d = T["sdet"][T["sdet"].sample_key == sample_key][cols]
    rj = T["r1rej"][T["r1rej"].sample_key == sample_key][["field_name","field_value","evidence_source","evidence_quote","reject_reason"]]
    dr = T["sdet_drop"][T["sdet_drop"].sample_key == sample_key][["field_name","value_normalized","evidence_source","evidence_quote","drop_reason"]]
    ad = T["adult"][T["adult"].sample_key == sample_key][["field_name","field_value","unit","age_days","evidence_source","evidence_quote","reason"]]
    sm = T["samples"][T["samples"].sample_key == sample_key]
    sj = T["subjects"][T["subjects"].sample_key == sample_key]
    wide = T["smw"][T["smw"].sample_key == sample_key]
    return dict(determinations=d, r1_rejected=rj, dropped_group=dr, adult_age=ad, sample=sm, subject=sj, wide=wide)

# ---------------- paper level ----------------
def find_paper(T, ident, kind):
    P = T["papers"]
    if kind == "pmid": h = P[P.pmid.astype(str).str.replace(r"\.0$","",regex=True) == ident]
    elif kind == "pmcid": h = P[P.pmcid.astype(str).str.upper() == ident.upper()]
    elif kind == "doi": h = P[P.doi.astype(str).str.lower() == ident.lower()]
    else:
        toks = [t for t in re.findall(r"[A-Za-z]{4,}", ident)]
        mask = pd.Series(True, index=P.index)
        for t in toks[:6]: mask &= P.title.fillna("").str.contains(t, case=False, regex=False)
        h = P[mask]
    return h

def paper_links(T, paper_ids):
    ids = set(str(p) for p in paper_ids)
    rows = []
    for k in ["psl","psl_new","psl_new2"]:
        d = T[k][T[k].paper_id.astype(str).isin(ids)]
        for _, x in d.iterrows():
            rows.append(dict(table=k, paper_id=x.paper_id, study_accession=x.study_accession, relation=x.relation, method=x.method,
                             confidence=x.confidence, contested=x.contested, accessions=x.accessions, evidence=ev_str(x.evidence)))
    d = T["spl"][T["spl"].paper_id.astype(str).isin(ids)]
    for _, x in d.iterrows(): rows.append(dict(table="spl", paper_id=x.paper_id, study_accession=x.study_accession))
    sb = T["snowball"][T["snowball"].paper_id.astype(str).isin(ids)]
    return pd.DataFrame(rows), sb

def find_accessions_in_text(text):
    pats = {"bioproject": r"PRJ[EDN][A-Z]\d+", "run": r"[SED]RR\d{5,}", "sample": r"SAM[NED][A-Z]?\d+|[SED]RS\d{5,}",
            "secondary_study": r"[SED]RP\d{5,}", "experiment": r"[SED]RX\d{5,}", "gsa": r"CRA\d{6}|PRJCA\d+", "dbgap": r"phs\d{6}", "ega": r"EGA[SD]\d{11}"}
    return {k: sorted(set(re.findall(p, text or ""))) for k, p in pats.items() if re.findall(p, text or "")}

# ---------------- findings ----------------
def add_finding(path, identifier, finding_type, current_state, proposed_change, evidence_quote, evidence_source, confidence):
    assert finding_type in {"triage_error","missing_paper","value_error","coverage_gap","universe_miss","other"}
    df = pd.read_csv(path) if pd.io.common.file_exists(path) else pd.DataFrame(columns=FIND_COLS)
    row = dict(date=datetime.date.today().isoformat(), identifier=identifier, finding_type=finding_type, current_state=current_state,
               proposed_change=proposed_change, evidence_quote=evidence_quote, evidence_source=evidence_source, confidence=confidence)
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df.to_csv(path, index=False)
    return len(df)

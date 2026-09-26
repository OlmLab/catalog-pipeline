"""R1' : rebuild route-R1 determinations for a study list.
  (a) keep existing deterministic biosample_attr rows (r1_determinations.parquet) for the studies,
  (b) replace sample_name_convention rows with r1_title_parser output (DOL/day tokens > ordinals),
  (c) resolve unitless numeric ages (r1_rejected 'bare number, no unit key') by two deterministic rules:
        U1 sibling-attribute: a same-sample attribute whose key names the unit (host_age_days,
           host_age_normalized_years, age_units) agrees numerically (ratio within 2%) -> that unit;
        U2 unique-admissible-unit: over the study's value distribution, exactly one unit in
           {days, weeks, months, years} places >=90% of values inside 0-1100 d AND every other
           unit places <=30% inside -> that unit (study is an included infant cohort).
      Unresolved studies are exported for R3 (paper states the unit).
Usage: python -c "import r1_prime; r1_prime.run(studies, paths)"  (see run() signature)
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
import re, json
import pandas as pd, numpy as np
from r1_title_parser import parse_sample_name, FACT

TITLE_CONF = {"unit_word": 0.85, "birth_word": 0.8, "compact_letter": 0.65}


def title_rows(samples):
    rows = []
    for r in samples.itertuples(index=False):
        for src, txt in (("sample.title", r.sample_title), ("sample.library_name", r.library_name)):
            if not isinstance(txt, str) or not txt.strip():
                continue
            p = parse_sample_name(txt)
            if p["subject_id"]:
                rows.append(dict(sample_key=r.sample_key, study_accession=r.study_accession, field_name="subject_id", field_value=txt,
                                 value_normalized=p["subject_id"], confidence=0.7, evidence_source=src, evidence_locator="sample_id_pattern",
                                 evidence_quote=txt[:80], determined_by="r1_title_parser", route="R1", parse_note="subject_ordinal"))
            if p["timepoint_label"]:
                rows.append(dict(sample_key=r.sample_key, study_accession=r.study_accession, field_name="timepoint_label", field_value=txt,
                                 value_normalized=p["timepoint_label"], confidence=0.7, evidence_source=src, evidence_locator="sample_id_pattern",
                                 evidence_quote=txt[:80], determined_by="r1_title_parser", route="R1", parse_note=p["tag"] or "timepoint_only"))
            if p["age_days"] is not None and not p["is_mother"] and 0 <= p["age_days"] <= 1100:
                rows.append(dict(sample_key=r.sample_key, study_accession=r.study_accession, field_name="age_at_collection_days", field_value=txt,
                                 value_normalized=str(p["age_days"]), confidence=TITLE_CONF[p["tag"]], evidence_source=src, evidence_locator="sample_id_pattern",
                                 evidence_quote=p["timepoint_label"] or txt[:80], determined_by="r1_title_parser", route="R1",
                                 parse_note=f"{p['tag']}:{p['number']:g} {p['unit']}"))
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # policy: compact single-letter tokens (D6, M4, 6m) are NOT committed as ages by R1' (PRJNA301903 D6
    # contradicted host_day_of_life in 51/52 samples); they survive as timepoint_label for R3 to interpret.
    df = df[~((df.field_name == "age_at_collection_days") & df.parse_note.str.startswith("compact"))]
    return df


def resolve_units(rej, attrs, samples):
    """rej: r1_rejected rows for age with 'bare number' reason. Returns (resolved_rows, rules_table, unresolved_studies)."""
    out, rules, unresolved = [], [], []
    for (s, key), d in rej.groupby(["study_accession", "evidence_locator"]):
        v = pd.to_numeric(d.field_value, errors="coerce")
        d = d.assign(v=v).dropna(subset=["v"])
        unit, rule, ev = None, None, None
        # U1 sibling attribute
        sk = set(d.sample_key)
        sib = attrs[attrs.sample_key.isin(sk) & attrs.attr_key_norm.str.contains(r"age.*(?:day|week|month|year)|(?:day|week|month|year).*age|age_unit", regex=True)]
        for k2, d2 in sib.groupby("attr_key_norm"):
            u2 = next((u for u in ("days", "weeks", "months", "years") if u[:-1] in k2), None)
            if k2.endswith("age_units") or k2 == "age_unit":
                vals = d2.attr_value.astype(str).str.lower().str.strip().unique()
                if len(vals) == 1 and vals[0].rstrip("s") + "s" in FACT:
                    unit, rule, ev = vals[0].rstrip("s") + "s", "U1_sibling_unit_attr", f"sample.attr.{k2}={vals[0]}"
                    break
                continue
            if not u2:
                continue
            m = d.merge(d2[["sample_key", "attr_value"]], on="sample_key")
            m["v2"] = pd.to_numeric(m.attr_value, errors="coerce")
            m = m.dropna(subset=["v2"])
            if len(m) >= 5:
                for u in ("days", "weeks", "months", "years"):
                    ratio = ((m.v * FACT[u]) / (m.v2 * FACT[u2]).replace(0, np.nan)).dropna()
                    if len(ratio) >= 5 and (ratio.between(0.97, 1.03)).mean() >= 0.9:
                        unit, rule, ev = u, "U1_sibling_attr_numeric", f"sample.attr.{k2} ({u2}) agrees with host value in {u} ({int((ratio.between(0.97,1.03)).sum())} samples)"
                        break
                if unit:
                    break
        # U2 unique admissible unit
        if unit is None:
            fr = {u: float(((d.v * f) <= 1100).mean()) for u, f in FACT.items() if u != "hours"}
            adm = [u for u, x in fr.items() if x >= 0.9]
            others_low = all(x <= 0.3 for u, x in fr.items() if u not in adm)
            if len(adm) == 1 and others_low:
                unit, rule, ev = adm[0], "U2_unique_admissible_unit", f"distribution: median={d.v.median():g} n={len(d)} frac_in_range={json.dumps({k: round(x,2) for k,x in fr.items()})}"
        rules.append(dict(study_accession=s, attr_key=key, n=len(d), unit=unit, rule=rule, evidence=ev,
                          median=float(d.v.median()), max=float(d.v.max()), frac_le36=float((d.v <= 36).mean())))
        if unit is None:
            unresolved.append(dict(study_accession=s, attr_key=key, n=len(d), examples=d.v.round(2).head(12).tolist(), median=float(d.v.median()), max=float(d.v.max())))
            continue
        for r in d.itertuples(index=False):
            days = int(round(r.v * FACT[unit]))
            if 0 <= days <= 1100:
                out.append(dict(sample_key=r.sample_key, study_accession=s, field_name="age_at_collection_days", field_value=r.field_value,
                                value_normalized=str(days), confidence=0.75 if rule.startswith("U2") else 0.85, evidence_source="biosample_attr",
                                evidence_locator=key, evidence_quote=f"{key}={r.field_value} ({unit}; {rule})", determined_by="r1_unit_resolution",
                                route="R1", parse_note=f"{rule}: {ev}"[:200]))
    return pd.DataFrame(out), pd.DataFrame(rules), unresolved


def run(studies, r1_det, r1_rej, attrs, samples):
    studies = set(studies)
    base = r1_det[r1_det.study_accession.isin(studies) & (r1_det.evidence_source != "sample_name_convention")].copy()
    smp = samples[samples.study_accession.isin(studies)]
    trows = title_rows(smp)
    rej = r1_rej[r1_rej.study_accession.isin(studies) & (r1_rej.field_name == "age_at_collection_days") & r1_rej.reject_reason.str.contains("bare number")]
    ures, rules, unresolved = resolve_units(rej, attrs, smp)
    parts = [x for x in (base, trows, ures) if x is not None and len(x)]
    det = pd.concat(parts, ignore_index=True)
    det["value_normalized"] = det["value_normalized"].astype(str)
    return det, rules, unresolved

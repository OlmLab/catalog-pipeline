"""Run-level re-gate of accepted run-/library-keyed R2 tables (spec §5 step 2): the first-row collapse is disabled by
mapping table ids to RUN accessions instead of BioSamples; one candidate per run. Column->field classification is taken
from the already-accepted candidate rows (same table, same column) so no LLM call is needed; raw->normalized legends are
rebuilt from those rows and normalize() is the fallback for raw values not seen before.
Requires in namespace: tmr (accepted tables), colmap, rk (run-keyed candidates), runs/r63, sam, inv (supp inventory), HL, R2."""
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
import re, pandas as pd, numpy as np
import r2_supp_extract_v2 as R2

DATE_HDR = re.compile(r"date|sampling_day|collection", re.I)

def norm_fn(method):
    m = method.split(":")
    lvl = m[1] if m[0] == "orig" else m[0]
    lvl = lvl.replace("affix_", "")
    return {"exact": lambda s: str(s).strip(), "casefold": R2._n_case, "alnum": R2._n_alnum, "alnum_lz": R2._n_lz, "token": R2._n_alnum}.get(lvl, lambda s: str(s).strip()), lvl

def run_keys(study, fn):
    """norm(value) -> run_accession for the study's run/experiment/library values; ambiguous values dropped."""
    rn = r63[r63.study_accession == study]
    d = {}
    for c in ("run_accession", "experiment_accession", "library_name"):
        for v, ra in zip(rn[c], rn.run_accession):
            if isinstance(v, str) and v.strip():
                nv = fn(v)
                if nv:
                    d.setdefault(nv, set()).add(ra)
    return {k: next(iter(s)) for k, s in d.items() if len(s) == 1}

def regate(tables):
    """tables: DataFrame rows of tmr (accepted run/library keyed). Returns (per_run_rows DataFrame, log list)."""
    run2bs = dict(zip(r63.run_accession, r63.sample_key))
    out, log = [], []
    for t in tables.itertuples(index=False):
        st, pm, fl, sh = t.study_accession, t.pmcid, t.file, ("" if pd.isna(t.sheet) else str(t.sheet))
        tab = f"{pm}/{fl}/{sh}"
        zp = R2.zip_path(pm, HL)
        if zp is None:
            log.append(dict(tab=tab, study=st, status="zip_missing")); continue
        hri = inv_hri.get((pm, fl, sh), 0)
        hdr, body, err = R2.read_table(zp, fl, (sh or None), int(hri))
        if err:
            log.append(dict(tab=tab, study=st, status=err)); continue
        if t.id_col not in hdr:
            log.append(dict(tab=tab, study=st, status="id_col_missing")); continue
        j = hdr.index(t.id_col)
        fn, lvl = norm_fn(t.method)
        keys = run_keys(st, fn)
        ids = [r[j] if j < len(r) else None for r in body]
        hits = {}
        for i, v in enumerate(ids):
            if v is None or str(v).strip() == "":
                continue
            ra = keys.get(fn(v))
            if ra:
                hits[i] = ra
        cols = colmap[(colmap.study_accession == st) & (colmap.tab == tab)]
        legends = {}
        for c in cols.itertuples(index=False):
            sub = rk[(rk.study_accession == st) & (rk.tab == tab) & (rk.col == c.col) & (rk.field_name == c.field_name)]
            legends[(c.col, c.field_name)] = dict(zip(sub.field_value.astype(str).str.strip().str.lower(), sub.value_normalized))
        n_rows = 0
        for ri, ra in hits.items():
            bs = run2bs.get(ra)
            for c in cols.itertuples(index=False):
                if c.col not in hdr:
                    continue
                cj = hdr.index(c.col)
                raw = body[ri][cj] if cj < len(body[ri]) else None
                if raw is None or str(raw).strip() == "":
                    continue
                lg = legends[(c.col, c.field_name)]
                key = str(raw).strip().lower()
                if key in lg:
                    val, note = lg[key], c.note.split(";")[0] + "(legend_from_accepted)"
                else:
                    unit = None
                    m = re.match(r"age (days|weeks|months|years)", c.note)
                    if m: unit = m.group(1)
                    elif c.note.startswith("weeks"): unit = "weeks"
                    elif c.note.startswith("grams"): unit = "grams"
                    elif c.note.startswith("kg"): unit = "kg"
                    val, note = R2.normalize(c.field_name, raw, unit, {}, c.col)
                if val is None:
                    continue
                if c.field_name == "age_at_collection_days" and not (0 <= float(val) <= 1100):
                    continue
                if c.field_name == "gestational_age_weeks" and not (20 <= float(val) <= 45):
                    continue
                out.append(dict(run_accession=ra, sample_key=bs, study_accession=st, field_name=c.field_name, field_value=str(raw)[:120],
                                value_normalized=str(val), confidence=min(float(c.conf), 0.75), evidence_source="paper.supp.table",
                                evidence_locator=f"{tab}!{c.col}:{ri + 1}", evidence_quote=f"{c.col}={str(raw)[:60]}",
                                determined_by="r2_regate_run_level+det_norm", route="R2", scope="sample",
                                parse_note=f"{note}; map={t.method.replace('orig:', '')}; per-run", pmcid=pm, tab=tab, method=t.method))
                n_rows += 1
        # date-like columns (criterion 2: collection_date) -> conflict log only
        for cj, h in enumerate(hdr):
            if DATE_HDR.search(str(h)) and cj != j and h not in set(cols.col):
                vals = [(ri, body[ri][cj]) for ri in hits if cj < len(body[ri])]
                parsed = [(ri, R2._date_norm(v)) for ri, v in vals if v not in (None, "")]
                parsed = [(ri, d) for ri, d in parsed if d]
                if len(parsed) >= 3:
                    for ri, d in parsed:
                        out.append(dict(run_accession=hits[ri], sample_key=run2bs.get(hits[ri]), study_accession=st, field_name="collection_date",
                                        field_value=str(body[ri][cj])[:60], value_normalized=d, confidence=0.75, evidence_source="paper.supp.table",
                                        evidence_locator=f"{tab}!{h}:{ri + 1}", evidence_quote=f"{h}={str(body[ri][cj])[:60]}",
                                        determined_by="r2_regate_run_level+date_norm", route="R2", scope="sample",
                                        parse_note=f"date; map={t.method.replace('orig:', '')}; per-run; conflict_log_only", pmcid=pm, tab=tab, method=t.method))
        log.append(dict(tab=tab, study=st, status="ok", n_hits=len(hits), n_runs_mapped=len(set(hits.values())), n_biosamples=len({run2bs.get(r) for r in hits.values()}),
                        n_rows=n_rows, n_cols=len(cols), norm=lvl))
    return pd.DataFrame(out), pd.DataFrame(log)

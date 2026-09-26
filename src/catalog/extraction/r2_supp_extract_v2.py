"""R2 (v2): per-sample determinations from supplementary tables of papers linked to a study.

v2 change (2026-09-25): the default ID gate is the attribute inverted-index mapper (build_attr_index / map_table /
choose, formerly r2_rescue_map.py): per column it tries orig (accession, library_name, sample_title, subject_id_raw)
-> attr_exact (any archive attribute value) -> attr_norm -> composite (subject + timepoint/date attribute pair)
-> subject (subject-level join, static fields only, confidence -0.1, parse_note "subject_level_join").
gate(..., legacy=True) or attrs=None reproduces the pilot gate exactly. Wide abundance matrices (>200 numeric
columns, no header field hits) are skipped; per_table_budget seconds caps each table (SIGALRM).

Driven by a study list. Pipeline per (study, table):
  1. table candidates = supp_inventory rows (has_sample_id_final) whose pmcid is linked to the study
  2. read the whole table (col_reader.read_rows from the cached EPMC supplementary ZIP)
  3. ID mapping: try sid_col first, then every other column; keys = study's own sample/secondary/run/
     experiment accessions, library_name, sample_title, subject_id_raw; methods exact -> casefold ->
     alnum -> leading-zero-stripped digit groups -> common prefix/suffix stripped -> token (>=4 chars,
     unique). A table counts only if >=50% of its non-empty IDs map to THIS study (and >=3 matches).
  4. Haiku classifies columns -> target fields (<=15 tables per request), with a coding legend for
     coded values; deterministic normalisation (r1_parsers) with the legend as fallback.
  5. Emit rows: evidence_source='paper.supp.table', evidence_locator='<pmcid>/<file>/<sheet>!<col>:<row>',
     evidence_quote='<header>=<cell>'. Subject-level tables (mapped via subject id) only propagate
     static fields (delivery, preterm, GA, birth weight, sex, country, maternal_antibiotics).
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
import os, re, io, json, zipfile, math
import pandas as pd, numpy as np
import col_reader as CR, supp_parse as SP, r1_parsers as RP
import llm_batch_common as LBC

HAIKU = resolve_model("screen")
FIELDS = ["age_at_collection_days", "delivery_mode", "feeding_mode", "preterm_status", "gestational_age_weeks",
          "birth_weight_grams", "antibiotic_exposure", "maternal_antibiotics", "probiotic_exposure",
          "hmo_supplementation", "nec_status", "country", "sex", "subject_id", "timepoint_label"]
STATIC = {"delivery_mode", "preterm_status", "gestational_age_weeks", "birth_weight_grams", "sex", "country", "maternal_antibiotics", "subject_id"}
VOCAB = {"delivery_mode": {"vaginal", "c_section", "c_section_elective", "c_section_emergency"},
         "feeding_mode": {"exclusive_breast", "mixed", "formula", "weaned"},
         "preterm_status": {"preterm", "term"}, "sex": {"male", "female"}}
YESNO = {"antibiotic_exposure", "maternal_antibiotics", "probiotic_exposure", "hmo_supplementation", "nec_status"}
ZIP_DIR = "supp_zips"


# ------------------------------------------------------------------ ID normalisation
def _n_case(s): return str(s).strip().casefold()
def _n_alnum(s): return re.sub(r"[^a-z0-9]", "", _n_case(s))
def _n_lz(s): return re.sub(r"(?<![0-9])0+(?=[0-9])", "", _n_alnum(s))
NORMS = [("exact", lambda s: str(s).strip()), ("casefold", _n_case), ("alnum", _n_alnum), ("alnum_lz", _n_lz)]


def study_keys(study, samples, runs):
    """dict: norm_level -> {norm_id: (sample_key, kind)}; kinds: sample|run|library|title|subject."""
    smp = samples[samples.study_accession == study]
    rn = runs[runs.study_accession == study]
    pairs = []
    for c, kind in (("sample_key", "sample"), ("secondary_sample", "sample"), ("library_name", "library"), ("sample_title", "title"), ("subject_id_raw", "subject")):
        if c in smp:
            pairs += [(v, k, kind) for v, k in zip(smp[c], smp.sample_key) if isinstance(v, str) and v.strip()]
    for c, kind in (("run_accession", "run"), ("experiment_accession", "run"), ("secondary_sample_accession", "sample"), ("sample_accession", "sample"), ("library_name", "library")):
        if c in rn:
            m = rn.dropna(subset=[c])
            # map run rows to sample_key via sample_accession (SAMN/SAMEA) or secondary
            sec2key = dict(zip(smp.secondary_sample, smp.sample_key))
            skset = set(smp.sample_key)
            sk = [a if a in skset else sec2key.get(b) for a, b in zip(m.sample_accession, m.secondary_sample_accession)]
            pairs += [(v, k, kind) for v, k in zip(m[c], sk) if isinstance(v, str) and isinstance(k, str)]
    # generic values (shared by >1 DISTINCT sample) are useless as keys. Count distinct sample_keys per value, not
    # occurrences: a sample with several runs repeats its accession/library once per run row and was wrongly dropped.
    uniq = {}
    for v, k, kind in pairs:
        uniq.setdefault(v, set()).add(k)
    pairs = list(dict.fromkeys((v, k, kind) for v, k, kind in pairs if len(uniq[v]) == 1 or kind == "subject"))
    levels = {}
    for name, fn in NORMS:
        d = {}
        for v, k, kind in pairs:
            nv = fn(v)
            if not nv:
                continue
            if nv in d and d[nv][0] != k and kind != "subject":
                d[nv] = (None, "ambiguous")
            elif kind == "subject":
                d.setdefault(nv, ([], "subject"))
                if isinstance(d[nv][0], list):
                    d[nv][0].append(k)
            else:
                d.setdefault(nv, (k, kind))
        levels[name] = d
    # token index (>=4 chars) from library/title split on separators, unique only
    tok = {}
    for v, k, kind in pairs:
        if kind in ("library", "title", "sample"):
            for t in re.split(r"[._\-\s/|:]+", str(v)):
                t2 = _n_alnum(t)
                if len(t2) >= 4:
                    tok.setdefault(t2, set()).add(k)
    levels["token"] = {t: (next(iter(s)), "token") for t, s in tok.items() if len(s) == 1}
    return levels


def _strip_affix(ids):
    """common prefix/suffix across the table's ids (only if it leaves >=2 chars)."""
    s = [str(i) for i in ids if i]
    if len(s) < 3:
        return ids
    pre = os.path.commonprefix(s)
    suf = os.path.commonprefix([x[::-1] for x in s])[::-1]
    out = []
    for x in ids:
        y = str(x)
        if pre and y.startswith(pre) and len(y) - len(pre) >= 2:
            y = y[len(pre):]
        if suf and y.endswith(suf) and len(y) - len(suf) >= 2:
            y = y[:-len(suf)]
        out.append(y)
    return out


def map_ids(ids, levels):
    """Return (method, {row_index: sample_key or [sample_keys]}, rate, n_nonempty)."""
    clean = [None if (v is None or str(v).strip() == "" or str(v).strip().lower() in ("nan", "na", "none")) else str(v).strip() for v in ids]
    nz = [i for i, v in enumerate(clean) if v]
    if len(nz) < 3:
        return None, {}, 0.0, len(nz)
    best = (None, {}, 0.0)
    variants = [("", clean), ("affix_", _strip_affix(clean))]
    for vname, vals in variants:
        for name, fn in NORMS + [("token", _n_alnum)]:
            d = levels[name]
            hits, kind = {}, ""
            for i in nz:
                nv = fn(vals[i])
                if nv in d and d[nv][0] is not None:
                    hits[i] = d[nv][0]
                    kind = d[nv][1]
            rate = len(hits) / len(nz)
            if rate > best[2]:
                best = (vname + name + ":" + kind, hits, rate)
            if rate >= 0.95:
                return best[0], best[1], best[2], len(nz)
    return best[0], best[1], best[2], len(nz)



# ================================================================== extended ID gate (v2: attribute inverted index)
import r1_parsers as RP

NORM_FN = dict(NORMS)

ID_LIKE = re.compile(r"subject|participant|individual|patient|infant|child|baby|host_id|donor|family|mother|twin|pair|person|volunteer|kid|neonate|newborn|_id$|^id$|\bid\b|identifier|name|alias|code|barcode|label|sample|specimen|library|tube|isolate|strain|title", re.I)
BLACKLIST = re.compile(r"^(tax_id|scientific_name|organism|center_name|ena_.*|checklist|ena_checklist|project_name|biosamplemodel|ncbi_submission_package|insdc_.*|bioproject|study.*|sex|gender|country|geo_loc_name|body_site|host|host_tax_id|host_taxid|host_scientific_name|sample_type|isolation_source|env_.*|lat_lon|description|host_age|age|host_age_unit|.*age.*|.*weight.*|.*delivery.*|.*feeding.*|.*antibiotic.*|.*gestation.*|collection_date|.*date.*|sample_name_taxon_id|sample_name_scientific_name|broker_name|investigation_type|sequencing_method|library_.*|instrument.*|platform|status|host_status|disease|phenotype|host_phenotype|tissue|material|elevation|depth|altitude|temperature|ph|source_material_id|collected_by|submitted_.*|sra_accession|biosample_accession|first_public|last_update)$", re.I)
ID_LIKE_KEY = re.compile(r"(^|_)id($|_)|identifier|alias|barcode|(^|_)name($|_)|label|(^|_)code($|_)|subject|participant|patient|donor|individual|family|twin|pair|(infant|child|baby|neonate|newborn|kid|mother|host|sample|specimen|library|tube|isolate)_?(id|n|nr|no|num|number|code)($|_)", re.I)
COMP_KEYS = re.compile(r"time|visit|age|day|week|month|date|dol|point|stage|sampling|collection|period|phase", re.I)
SHORT_NUM = re.compile(r"^[-+]?\d+(\.\d+)?$")   # any pure number: not an identifier unless the key name says so
RELATIONAL = re.compile(r"mother|father|partner|sibling|parent|spouse|donor|recipient|match|twin_id|pair_id|maternal|paternal", re.I)


DATE_RX = re.compile(r"^\s*(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|\d{1,2}[ -][A-Za-z]{3,9}[ -,]+\d{2,4}|[A-Za-z]{3,9}[ -]\d{1,2},?[ -]\d{2,4})")
_DATE_CACHE = {}


def _date_norm(s):
    s = str(s).strip()
    if s in _DATE_CACHE:
        return _DATE_CACHE[s]
    if not DATE_RX.match(s):
        _DATE_CACHE[s] = None
        return None
    r = _date_norm_slow(s)
    _DATE_CACHE[s] = r
    return r


def _date_norm_slow(s):
    try:
        d = pd.to_datetime(s, errors="coerce")
    except Exception:
        return None
    if d is pd.NaT or d is None or pd.isna(d):
        return None
    return d.strftime("%Y%m%d")


def _digits(s):
    d = re.sub(r"\D", "", str(s))
    return d.lstrip("0") or ("0" if d else "")


def build_attr_index(study, samples, attrs):
    """Per-study inverted index. Returns dict with
       levels: {norm_name: {norm_value: {attr_key: set(sample_keys)}}}
       key_info: {attr_key: dict(n_vals, n_distinct, unique_per_sample, id_like, short_numeric)}
       sample_attrs: {sample_key: {attr_key: [values]}} (for composite joins)"""
    smp = samples[samples.study_accession == study]
    sk = set(smp.sample_key)
    a = attrs[attrs.sample_key.isin(sk)][["sample_key", "attr_key_norm", "attr_value"]].dropna()
    a = a[a.attr_value.astype(str).str.strip().ne("")]
    a = a[~a.attr_value.astype(str).map(RP.is_null)]
    # add sample_title / library_name / alias from the samples table (alias may already be in attrs)
    extra = []
    for c, k in (("sample_title", "sample_title"), ("library_name", "library_name"), ("subject_id_raw", "subject_id_raw"), ("secondary_sample", "secondary_sample")):
        if c in smp:
            extra.append(pd.DataFrame({"sample_key": smp.sample_key, "attr_key_norm": k, "attr_value": smp[c]}).dropna())
    a = pd.concat([a] + extra, ignore_index=True).drop_duplicates()
    a["attr_value"] = a.attr_value.astype(str).str.strip()
    n_s = len(sk)
    key_info, levels = {}, {n: {} for n, _ in NORMS}
    levels["date"] = {}
    sample_attrs = {}
    for key, g in a.groupby("attr_key_norm"):
        vals = g.attr_value
        nd = vals.nunique()
        if nd < 2 or BLACKLIST.match(key) and not ID_LIKE_KEY.search(key):
            # blacklisted keys are still usable for composite joins (dates/timepoints) -> keep in sample_attrs
            for s_, v_ in zip(g.sample_key, vals):
                sample_attrs.setdefault(s_, {}).setdefault(key, []).append(v_)
            key_info[key] = dict(n_vals=len(g), n_distinct=nd, unique_per_sample=False, id_like=bool(ID_LIKE_KEY.search(key)), short_numeric=bool(vals.map(lambda x: bool(SHORT_NUM.match(x))).all()), indexable=False)
            continue
        per_val = g.groupby("attr_value").sample_key.apply(set)
        maxsz = per_val.map(len).max()
        unique = bool(maxsz == 1)
        short_num = bool(vals.map(lambda x: bool(SHORT_NUM.match(x))).all())
        idl = bool(ID_LIKE_KEY.search(key))
        indexable = idl or not short_num
        key_info[key] = dict(n_vals=len(g), n_distinct=nd, unique_per_sample=unique, id_like=idl, short_numeric=short_num, indexable=indexable)
        for s_, v_ in zip(g.sample_key, vals):
            sample_attrs.setdefault(s_, {}).setdefault(key, []).append(v_)
        if not indexable:
            continue
        for lname, fn in NORMS:
            d = levels[lname]
            for v, ss in per_val.items():
                nv = fn(v)
                if nv:
                    d.setdefault(nv, {}).setdefault(key, set()).update(ss)
        for v, ss in per_val.items():
            dn = _date_norm(v)
            if dn:
                levels["date"].setdefault(dn, {}).setdefault(key, set()).update(ss)
    return dict(levels=levels, key_info=key_info, sample_attrs=sample_attrs, n_samples=n_s, sample_keys=sk)


COUNT_LIKE = re.compile(r"number|count|^n\b|^#|\bn_|^n[A-Z_]|abundance|p[- ]?value|stat|mean|median|depth|reads|size|total|percent|%|ratio|score|value|group|year|age|weight|length|coverage|rpkm|cpm|tpm|freq|prop|index|nmds|pc\d|axis|^col\d+$", re.I)


def _plausible_numeric_id_col(header, vals, nz, per_sample):
    """A table column of bare numbers can only be an identifier column when its header names an
    identifier (subject/infant/sample/id ...) and not a count/statistic, and (per-sample keys) its values are unique."""
    if not header or not ID_LIKE.search(str(header)) or COUNT_LIKE.search(str(header)):
        return False
    if per_sample:
        vv = [vals[i] for i in nz]
        return len(set(vv)) >= 0.9 * len(vv)
    return True


def _clean_ids(ids):
    clean = [None if (v is None or RP.is_null(str(v))) else str(v).strip() for v in ids]
    nz = [i for i, v in enumerate(clean) if v]
    return clean, nz


def map_attr(ids, idx, allow_subject=True, header=None):
    """(a)+(b)+(d): return list of candidate results dict(method, matched_attr_key, hits, rate, n, subject_level)."""
    clean, nz = _clean_ids(ids)
    out = []
    if len(nz) < 3:
        return out, len(nz)
    variants = [("", clean), ("affix_", _strip_affix(clean))]
    aln = idx["levels"]["alnum"]
    for vname, vals in variants:
        # numeric test on the variant actually matched: "30 min" -> affix-stripped "30" is a bare number
        col_numeric = sum(1 for i in nz if SHORT_NUM.match(str(vals[i]))) >= 0.9 * len(nz)
        ov = len({_n_alnum(vals[i]) for i in nz} & set(aln))
        has_date = bool(idx["levels"]["date"]) and sum(1 for i in nz[:200] if DATE_RX.match(vals[i])) >= 3
        if ov < 3 and not has_date:
            continue
        for lname, fn in NORMS + [("date", _date_norm)]:
            d = idx["levels"][lname]
            if not d:
                continue
            if lname == "date" and not has_date:
                continue
            # count hits per attr key
            per_key = {}
            for i in nz:
                nv = fn(vals[i])
                if not nv or nv not in d:
                    continue
                for key, ss in d[nv].items():
                    per_key.setdefault(key, {})[i] = ss
            for key, hits in per_key.items():
                info = idx["key_info"][key]
                if (col_numeric or info["short_numeric"]) and not _plausible_numeric_id_col(header, vals, nz, info["unique_per_sample"]):
                    continue
                if not (header and ID_LIKE.search(str(header)) and not COUNT_LIKE.search(str(header))):
                    # under a non-identifier header, bare-number hits are coincidences (e.g. "30 min" -> library "30")
                    hits = {i: ss for i, ss in hits.items() if not SHORT_NUM.match(str(vals[i]))}
                    if len(hits) < 3:
                        continue
                if info["unique_per_sample"]:
                    h = {i: next(iter(ss)) for i, ss in hits.items() if len(ss) == 1}
                    subj = False
                else:
                    # a non-unique attribute: per-sample assignment impossible; subject-level only
                    if not allow_subject or not info["id_like"] or info["n_distinct"] < 3:
                        continue
                    # the matched values must be non-unique in the table too OR the key is id-like
                    h = {i: sorted(ss) for i, ss in hits.items()}
                    subj = True
                rate = len(h) / len(nz)
                meth = ("attr_exact" if lname == "exact" else "attr_norm") + (":" + vname + lname if lname != "exact" or vname else "")
                out.append(dict(method=meth + (":subject" if subj else ""), matched_attr_key=key, hits=h, rate=rate, n=len(nz), subject_level=subj, level=lname, variant=vname))
    out.sort(key=lambda r: (r["subject_level"], -r["rate"], r["level"] != "exact"))
    return out, len(nz)


def composite(sub_hits, body, hdr, idx, exclude_cols):
    """(c): sub_hits {row: [sample_keys]} from a subject-level match; find a second column whose value
    selects exactly one sample within the subject's sample set via some attribute key.
    Returns best dict(col, attr_key, hits{row: sample_key}, rate) or None."""
    rows = list(sub_hits.keys())
    if not rows:
        return None
    sa = idx["sample_attrs"]
    # candidate attribute keys: those that vary within subjects
    cand_keys = set()
    for r in rows[:200]:
        ks = sub_hits[r]
        if len(ks) < 2:
            continue
        seen = {}
        for s in ks:
            for k, vs in sa.get(s, {}).items():
                seen.setdefault(k, set()).update(vs)
        for k, vs in seen.items():
            if len(vs) > 1:
                cand_keys.add(k)
    if not cand_keys:
        return None
    best = None
    ncols = len(hdr)
    # normalised value pools of candidate keys (over the subjects' samples)
    pool = {}
    subj_samples = {s for r in rows for s in sub_hits[r]}
    for s in subj_samples:
        for k, vs in sa.get(s, {}).items():
            if k in cand_keys:
                for v in vs:
                    pool.setdefault("alnum_lz", set()).add(_n_lz(v)); pool.setdefault("casefold", set()).add(_n_case(v))
                    pool.setdefault("digits", set()).add(_digits(v))
                    dn = _date_norm(v)
                    if dn: pool.setdefault("date", set()).add(dn)
    for j in range(min(ncols, 60)):
        if j in exclude_cols:
            continue
        col = [body[r][j] if j < len(body[r]) else None for r in rows]
        if sum(1 for c in col if c not in (None, "")) < 3:
            continue
        for lname, fn in [("casefold", _n_case), ("alnum_lz", _n_lz), ("date", _date_norm), ("digits", _digits)]:
            if lname == "date" and not (pool.get("date") and sum(1 for c in col[:200] if c and DATE_RX.match(str(c))) >= 3):
                continue
            tv = [fn(c) if c not in (None, "") else None for c in col]
            if len({t for t in tv if t} & pool.get(lname, set())) < 2:
                continue
            per_key = {}
            for r, t in zip(rows, tv):
                if not t:
                    continue
                for s in sub_hits[r]:
                    for k, vs in sa.get(s, {}).items():
                        if k not in cand_keys:
                            continue
                        for v in vs:
                            nv = fn(v)
                            if nv and nv == t:
                                per_key.setdefault(k, {}).setdefault(r, set()).add(s)
            for k, h in per_key.items():
                uniq = {r: next(iter(s)) for r, s in h.items() if len(s) == 1}
                rate = len(uniq) / len(rows)
                if best is None or rate > best["rate"]:
                    best = dict(col=j, attr_key=k, hits=uniq, rate=rate, level=lname)
        if best and best["rate"] >= 0.95:
            break
    return best


META_HDR = re.compile(r"age|deliver|birth|caesar|cesar|c-?section|vaginal|feed|breast|formula|milk|gestat|preterm|prematur|antibiot|\bsex\b|gender|countr|weight|probiot|\bnec\b|necrotiz|\bterm\b|week|month|\bday|dol|hmo|oligosacch|timepoint|visit", re.I)


def _numeric_subject_ok(col_vals, hdr):
    """A bare-number column matched at subject level (non-unique key) is accepted only when it looks like a
    subject column of a metadata table: >=5 distinct values, distinct/rows >= 0.1, and at least one header that
    names a metadata field (taxa/ARG count tables with an 'infants' column have none)."""
    clean, nz = _clean_ids(col_vals)
    vv = [clean[i] for i in nz]
    if not vv or len(set(vv)) < 5 or len(set(vv)) < 0.1 * len(vv):
        return False
    return any(META_HDR.search(str(h)) for h in hdr)


def _attempt_ok(a, cols, hdr):
    """Subject-level matches: the column must look like a subject column (>=5 distinct values and either
    distinct/rows >= 0.1 or >=20 distinct); bare-number columns additionally need a metadata-like header."""
    if not a.get("subject_level"):
        return True
    _cl, _nz = _clean_ids(cols[a["col"]])
    vv = [_cl[i] for i in _nz]
    if len(set(vv)) < 5 or not (len(set(vv)) >= 0.1 * len(vv) or len(set(vv)) >= 20):
        return False
    if _nz and sum(1 for i in _nz if SHORT_NUM.match(_cl[i])) >= 0.9 * len(_nz):
        return _numeric_subject_ok(cols[a["col"]], hdr)
    return True


def map_table(hdr, body, sid_col, base_levels, idx, max_cols=40):
    """Try original methods, then (a)(b)(c)(d) per column. Return best accepted candidate or best attempt."""
    order = []
    if isinstance(sid_col, str) and sid_col in hdr:
        order.append(hdr.index(sid_col))
    order += [j for j in range(len(hdr)) if j not in order]
    order = order[:max_cols]
    # relational columns (mother_id, partner_id ...) never identify the row's own sample unless declared as the id column
    order = [j for j in order if not (RELATIONAL.search(str(hdr[j])) and hdr[j] != sid_col)]
    cols = {j: [r[j] if j < len(r) else None for r in body] for j in order}
    attempts = []
    # --- original methods (per-sample only; original subject_id_raw path kept as in pilot)
    for j in order:
        method, hits, rate, n = map_ids(cols[j], base_levels)
        if method:
            # bare-number columns (and any subject-level match) must sit under an identifier-like header, not a count/statistic
            _cl, _nz = _clean_ids(cols[j])
            _vals = _strip_affix(_cl) if method.startswith("affix_") else _cl   # test the variant that matched
            _num = _nz and sum(1 for i in _nz if SHORT_NUM.match(str(_vals[i]))) >= 0.9 * len(_nz)
            if (_num or ":subject" in method) and not _plausible_numeric_id_col(hdr[j], _cl, _nz, ":subject" not in method):
                continue
            attempts.append(dict(col=j, method="orig:" + method, matched_attr_key=None, hits=hits, rate=rate, n=n, subject_level=":subject" in method, stage="orig"))
    # --- (a)/(b) per-sample attribute matches, (d) subject-level
    subj_cands = []
    for j in order:
        cands, n = map_attr(cols[j], idx, header=hdr[j])
        for c in cands:
            c["col"] = j
            c["stage"] = "subject" if c["subject_level"] else ("attr_exact" if c["level"] == "exact" and not c["variant"] else "attr_norm")
            (subj_cands if c["subject_level"] else attempts).append(c)
    attempts = [a for a in attempts if _attempt_ok(a, cols, hdr)]
    subj_cands = [a for a in subj_cands if _attempt_ok(a, cols, hdr)]
    # --- (c) composite from the best subject-level candidates
    comp = []
    for c in sorted(subj_cands, key=lambda r: -r["rate"])[:3]:
        if c["rate"] < 0.5:
            continue
        b = composite(c["hits"], body, hdr, idx, {c["col"]})
        if b and len(b["hits"]) >= 3:
            comp.append(dict(col=c["col"], method=f"composite:{c['matched_attr_key']}+{b['attr_key']}:{b['level']}", matched_attr_key=f"{c['matched_attr_key']}+{b['attr_key']}", hits=b["hits"], rate=len(b["hits"]) / c["n"], n=c["n"], subject_level=False, stage="composite", time_col=b["col"]))
    attempts += comp + subj_cands
    return attempts


def choose(attempts, pooled_min=20):
    """Apply the gate in stage order orig -> attr_exact -> attr_norm -> composite -> subject."""
    stage_rank = {"orig": 0, "attr_exact": 1, "attr_norm": 2, "composite": 3, "subject": 4}
    acc = []
    for a in attempts:
        n_m = len(a["hits"])
        own = a["rate"] >= 0.5 and n_m >= 3
        # pooled gate: exact matches only, each sample matched by exactly one row (an ID column, not a covariate)
        uniq_targets = len(set(map(str, a["hits"].values()))) == n_m if not a["subject_level"] else False
        exact_acc = a["stage"] == "orig" and a["method"].split(":")[1].endswith("exact") and a["method"].endswith((":run", ":sample"))
        pooled = (not a["subject_level"]) and n_m >= pooled_min and (exact_acc or (a["stage"] == "attr_exact" and "exact" in a["method"] and uniq_targets))
        if own or pooled:
            a = dict(a); a["status"] = "mapped" if own else "mapped_pooled"; a["pooled"] = not own
            acc.append(a)
    if acc:
        # quality tier: exact identifier matches < normalised matches < token/affix/composite heuristics; then stage, rate, size
        def tier(a):
            m = a["method"]
            if "token" in m or "affix_" in m or a["stage"] == "composite":
                return 2
            if a["stage"] in ("orig", "attr_exact") and ":exact" in m or m.startswith("attr_exact"):
                return 0
            return 1
        acc.sort(key=lambda a: (a["subject_level"], a["pooled"], tier(a), stage_rank[a["stage"]], -a["rate"], -len(a["hits"])))
        return acc[0]
    if attempts:
        b = max(attempts, key=lambda a: (a["rate"], len(a["hits"])))
        b = dict(b); b["status"] = "below_gate" if len(b["hits"]) else "no_match"; b["pooled"] = False
        return b
    return None


# ------------------------------------------------------------------ table reading
def zip_path(pmcid, HL):
    os.makedirs(ZIP_DIR, exist_ok=True)
    p = os.path.join(ZIP_DIR, f"{pmcid}.zip")
    if not os.path.exists(p):
        r = HL.epmc_supplementary_zip(pmcid)
        if not r.get("ok"):
            return None
        open(p, "wb").write(r["body"])
    return p


def read_table(zp, member, sheet, header_row_index):
    try:
        rows = CR.read_rows(zp, member, sheet)
    except Exception as e:
        return None, None, f"read_error:{type(e).__name__}"
    if not rows or header_row_index >= len(rows):
        return None, None, "empty"
    hdr = [SP._clean(c) if c is not None else "" for c in rows[header_row_index]]
    hdr = [h if h else f"col{i}" for i, h in enumerate(hdr)]
    body = [[SP._clean(c) if c is not None else None for c in r] + [None] * (len(hdr) - len(r)) for r in rows[header_row_index + 1:]]
    body = [r for r in body if any(c not in (None, "") for c in r)]
    return hdr, body, None


# ------------------------------------------------------------------ Haiku column classification
_SYS_CANDIDATES = [os.path.join("pilot_prompts", "r2_column_classify_system.txt"), "r2_column_classify_system.txt", _prompt_path("r2_column_classify_system.txt")]
CLASSIFY_SYSTEM = next((open(p).read() for p in _SYS_CANDIDATES if os.path.exists(p)), None)

TOOL = {"name": "classify_tables", "description": "Map supplementary-table columns to infant-metadata fields.",
        "input_schema": {"type": "object", "properties": {"tables": {"type": "array", "items": {"type": "object", "properties": {
            "table_id": {"type": "string"},
            "columns": {"type": "array", "items": {"type": "object", "properties": {
                "header": {"type": "string"},
                "field": {"type": "string", "enum": FIELDS + ["none"]},
                "unit": {"type": "string", "enum": ["days", "weeks", "months", "years", "grams", "kg", "none"]},
                "legend": {"type": "array", "items": {"type": "object", "properties": {"raw": {"type": "string"}, "normalized": {"type": "string"}}, "required": ["raw", "normalized"]}},
                "note": {"type": "string"}}, "required": ["header", "field"]}}}, "required": ["table_id", "columns"]}}}, "required": ["tables"]}}


def build_classify_request(tables, system_text):
    """tables: list of dict(table_id, headers, sample_rows, sid_header, context)."""
    parts = []
    for t in tables:
        parts.append(f"TABLE {t['table_id']}\nfile: {t['file']} sheet: {t['sheet']}\nsample-id column: {t['sid_header']}\nheaders: {json.dumps(t['headers'])[:1500]}\nexample rows: {json.dumps(t['sample_rows'])[:2500]}\ndistinct values per column (up to 8): {json.dumps(t['distinct'])[:2500]}\n")
    return {"model": HAIKU, "system": system_text, "max_tokens": 6000, "temperature": 0,
            "tools": [TOOL], "tool_choice": {"type": "tool", "name": "classify_tables"},
            "messages": [{"role": "user", "content": "Classify the columns of each table. Only list columns that carry one of the fields; omit 'none' columns.\n\n" + "\n".join(parts)}]}


# ------------------------------------------------------------------ value normalisation
def normalize(field, raw, unit, legend, header):
    s = "" if raw is None else str(raw).strip()
    if RP.is_null(s):
        return None, "null"
    low = s.lower()
    if field == "feeding_mode" and (low in RP.YES or low in RP.NO or low in ("y", "n", "true", "false", "0", "1")):
        return None, "boolean_feeding_column"   # F2 precedes legends
    if legend and low in legend:
        return legend[low], "legend"
    if field == "age_at_collection_days":
        # F1 (pilot): age groups / ranges ("0 - 1 month", "6 months-1 yr", "12-24 months") are never a value
        if re.search(r"\d[^\d]{0,12}(?:-|–|to)\s*\d|\bgroup\b|<|>|≤|≥", low):
            return None, "range_or_group"
        u = unit if unit in ("days", "weeks", "months", "years") else CR.unit_from_header(header)
        d = CR.parse_age_value(s, u, LBC.V["age_to_days"])
        if d is None:
            d2, note = RP.parse_age_text(s)
            if note.startswith("range"):
                return None, "range_or_group"
            return (str(int(round(d2))), note) if d2 is not None else (None, "unparsed")
        return str(int(round(d))), f"age {u or 'embedded'}"
    if field == "gestational_age_weeks":
        v, note = RP.parse_ga(s, unit if unit in ("weeks", "days") else "weeks")
        return (None if v is None else str(v)), note
    if field == "birth_weight_grams":
        if unit == "kg" and re.fullmatch(RP.NUM, s):
            return str(int(round(float(s) * 1000))), "kg"
        v, note = RP.parse_bw(s)
        return (None if v is None else str(v)), note
    if field == "delivery_mode":
        return RP.parse_delivery(s)
    if field == "feeding_mode":
        # F2 (pilot): boolean breastfeeding / solids columns (is_bf=yes, started_solids=yes, breastfed=no) do not fix feeding_mode
        if low in RP.YES or low in RP.NO or low in ("y", "n", "true", "false", "0", "1"):
            return None, "boolean_feeding_column"
        v, n = RP.parse_feeding(s)
        return ("weaned" if v == "weaned/solids" else v), n
    if field == "preterm_status":
        if re.search(r"pre-?term|prematur", low): return "preterm", "text"
        if re.search(r"\bterm\b|full", low): return "term", "text"
        if re.fullmatch(RP.NUM, s):   # GA in weeks
            x = float(s)
            if 22 <= x <= 44: return ("preterm" if x < 37 else "term"), "from_ga"
        return RP.parse_yesno(s)[0] and ({"yes": "preterm", "no": "term"}[RP.parse_yesno(s)[0]], "yesno") or (None, "unparsed")
    if field == "nec_status":
        return RP.parse_nec(s)
    if field in YESNO:
        v, n = RP.parse_yesno(s, "antibiotic" if "antibiotic" in field else "")
        if v is None and re.fullmatch(RP.NUM, s):
            v, n = ("yes" if float(s) > 0 else "no"), "numeric_count"
        return v, n
    if field == "sex":
        return RP.parse_sex(s)
    if field == "country":
        return RP.parse_country(s)
    if field in ("subject_id", "timepoint_label"):
        return s[:60], "label"
    return None, "no_field"


# ------------------------------------------------------------------ main
POOLED_MIN = 20   # exact accession matches in a pooled (multi-study) table: cannot be false positives


FIELD_HDR = re.compile(r"age|deliver|birth|caesar|cesar|c-?section|vaginal|feed|breast|formula|milk|gestat|preterm|prematur|antibiot|\bsex\b|gender|countr|weight|probiot|\bnec\b|necrotiz|term|week|month|day|dol|hmo|oligosacch|timepoint|visit", re.I)
NUMRX = re.compile(r"^[-+]?\d*\.?\d+([eE][-+]?\d+)?$")


def wide_matrix(hdr, body):
    """Abundance-matrix heuristic: >200 numeric columns and no header field hits."""
    if len(hdr) <= 200 or any(FIELD_HDR.search(str(h)) for h in hdr):
        return False
    nnum = 0
    for j in range(len(hdr)):
        vals = [r[j] for r in body[:50] if j < len(r) and r[j] not in (None, "")]
        if vals and sum(1 for v in vals if NUMRX.match(str(v))) / len(vals) > 0.9:
            nnum += 1
            if nnum > 200:
                return True
    return False


class TableTimeout(Exception):
    pass


def gate(studies, worklist, samples, runs, HL, attrs=None, per_table_budget=None, skip_wide=True, legacy=False, max_rows=60000):
    """Stage 1 (v2). Default path: attribute inverted-index gate (map_table -> choose) which tries, per column,
    orig (accession/library/title/subject_id_raw) -> attr_exact -> attr_norm -> composite -> subject.
    attrs: long sample_attributes table (sample_key, attr_key_norm, attr_value). legacy=True or attrs=None
    reproduces the pilot gate (map_ids over the accession/library/title keys only).
    per_table_budget: seconds per table (SIGALRM; main thread only). Returns (mapping DataFrame, tables_ok)."""
    import signal, time as _t
    if attrs is None:
        legacy = True
    keys_cache, idx_cache, mapping_rows, tables_ok, read_cache = {}, {}, [], [], {}
    wl = worklist[worklist.study_accession.isin(set(studies))].drop_duplicates(["pmcid", "file", "sheet", "study_accession"])
    use_alarm = per_table_budget is not None
    if use_alarm:
        signal.signal(signal.SIGALRM, lambda s, f: (_ for _ in ()).throw(TableTimeout()))
    for t in wl.itertuples(index=False):
        st = t.study_accession
        t0 = _t.time()
        if st not in keys_cache:
            keys_cache[st] = study_keys(st, samples, runs)
            if not legacy:
                idx_cache[st] = build_attr_index(st, samples, attrs)
        sheet = "" if pd.isna(t.sheet) else str(t.sheet)
        rec = dict(study_accession=st, pmcid=t.pmcid, paper_id=t.paper_id, relation=t.relation, file=t.file, sheet=sheet, n_rows=None, id_col=None,
                   method=None, matched_attr_key=None, n_ids=0, n_mapped=0, rate=0.0, status=None, accepted=False, seconds=0.0)

        def fin(status):
            rec["status"] = status; rec["accepted"] = status.startswith("mapped"); rec["seconds"] = round(_t.time() - t0, 1)
            mapping_rows.append(rec)
        zp = zip_path(t.pmcid, HL)
        if zp is None:
            fin("zip_missing"); continue
        ck = (t.pmcid, t.file, sheet)
        if use_alarm:
            signal.alarm(int(per_table_budget))
        try:
            if ck not in read_cache:
                read_cache[ck] = read_table(zp, t.file, t.sheet if not pd.isna(t.sheet) else None, int(t.header_row_index or 0))
            hdr, body, err = read_cache[ck]
            if err:
                fin(err); continue
            rec["n_rows"] = len(body)
            if len(body) > max_rows:
                fin("too_large"); continue
            if skip_wide and wide_matrix(hdr, body):
                fin("wide_matrix_skipped"); continue
            sid = t.sid_col if isinstance(t.sid_col, str) else None
            if legacy:
                b = _legacy_choose(hdr, body, sid, keys_cache[st])
            else:
                b = choose(map_table(hdr, body, sid, keys_cache[st], idx_cache[st]))
        except TableTimeout:
            fin(f"timeout_{int(per_table_budget)}s"); continue
        except Exception as e:
            fin(f"map_error:{type(e).__name__}"); continue
        finally:
            if use_alarm:
                signal.alarm(0)
        if b is None:
            fin("no_match"); continue
        rec.update(id_col=hdr[b["col"]], method=b["method"], matched_attr_key=b.get("matched_attr_key"), n_ids=b["n"], n_mapped=len(b["hits"]), rate=round(b["rate"], 3))
        fin(b["status"])
        if rec["accepted"]:
            tables_ok.append(dict(table_id=f"T{len(tables_ok)}", study_accession=st, pmcid=t.pmcid, paper_id=t.paper_id, file=t.file, sheet=sheet, hdr=hdr, body=body,
                                  id_col=b["col"], hits=b["hits"], method=b["method"], sid_header=hdr[b["col"]], pooled=b.get("pooled", False),
                                  matched_attr_key=b.get("matched_attr_key"), stage=b.get("stage", "orig")))
    return pd.DataFrame(mapping_rows), tables_ok


def _legacy_choose(hdr, body, sid_col, levels):
    """Pilot gate: best column by map_ids over accession/library/title keys; >=50% & >=3, or exact accession pooled >=20."""
    order = []
    if isinstance(sid_col, str) and sid_col in hdr:
        order.append(hdr.index(sid_col))
    order += [j for j in range(len(hdr)) if j not in order]
    best = (None, None, {}, 0.0, 0)
    for j in order[:40]:
        col = [r[j] if j < len(r) else None for r in body]
        method, hits, rate, n = map_ids(col, levels)
        if rate > best[3]:
            best = (j, method, hits, rate, n)
        if rate >= 0.95:
            break
    j, method, hits, rate, n = best
    if j is None:
        return None
    exact_acc = bool(method) and method.split(":")[0].endswith("exact") and method.endswith((":run", ":sample"))
    if rate >= 0.5 and len(hits) >= 3:
        status, pooled = "mapped", False
    elif exact_acc and len(hits) >= POOLED_MIN:
        status, pooled = "mapped_pooled", True
    else:
        status, pooled = ("below_gate" if len(hits) else "no_match"), False
    return dict(col=j, method="orig:" + method, matched_attr_key=None, hits=hits, rate=rate, n=n, subject_level=":subject" in method, stage="orig", status=status, pooled=pooled)


def run(studies, worklist, samples, runs, HL, host, out_prefix="r2_pilot", system_text=None, batch=15, max_concurrency=6, gated=None, attrs=None, per_table_budget=None):
    LBC.HOST = host
    mapdf, tables_ok = gated if gated is not None else gate(studies, worklist, samples, runs, HL, attrs=attrs, per_table_budget=per_table_budget)
    print(f"[r2] tables read {len(mapdf)}, mapped {len(tables_ok)}", flush=True)
    if not tables_ok:
        return pd.DataFrame(), mapdf, {"requests": 0, "tokens": 0}
    # ---- Haiku classification
    reqs, metas = [], []
    for b in range(0, len(tables_ok), batch):
        chunk = tables_ok[b:b + batch]
        tabs = []
        for tb in chunk:
            hdr, body = tb["hdr"], tb["body"]
            distinct = {}
            for j, h in enumerate(hdr[:80]):
                vals = pd.Series([r[j] for r in body[:2000] if j < len(r) and r[j] not in (None, "")]).astype(str)
                u = vals.drop_duplicates().head(8).tolist()
                if u:
                    distinct[h] = u
            tabs.append(dict(table_id=tb["table_id"], file=tb["file"], sheet=tb["sheet"], sid_header=tb["sid_header"], headers=hdr[:80], sample_rows=[r[:80] for r in body[:3]], distinct=distinct))
        reqs.append(build_classify_request(tabs, system_text))
        metas.append({"ids": [tb["table_id"] for tb in chunk], "slots": ["r2_classify"]})
    classified = {}

    def make_rows(meta, parsed, res):
        out = []
        for tb in parsed.get("tables", []):
            classified[tb.get("table_id")] = tb.get("columns", [])
            out.append({"record_id": tb.get("table_id"), "slot": "r2_classify", "value": json.dumps(tb.get("columns", []))[:2000], "outcome": "predicted",
                        "confidence": 0.7, "evidence": [{"source": "paper.supp.table", "quote": "column headers"}], "model": HAIKU})
        for rid in meta["ids"]:
            if rid not in classified:
                out.append(LBC.V["sentinel_row"](rid, "r2_classify", HAIKU, note="missing_from_batch"))
        return out
    _, stats = LBC.run_batches(reqs, metas, make_rows, f"{out_prefix}_classify_log.parquet", HAIKU, max_concurrency=max_concurrency)
    # re-run missing at batch 5
    missing = [tb for tb in tables_ok if tb["table_id"] not in classified]
    if missing:
        reqs2, metas2 = [], []
        for b in range(0, len(missing), 5):
            chunk = missing[b:b + 5]
            tabs = [dict(table_id=tb["table_id"], file=tb["file"], sheet=tb["sheet"], sid_header=tb["sid_header"], headers=tb["hdr"][:60], sample_rows=[r[:60] for r in tb["body"][:3]], distinct={}) for tb in chunk]
            r = build_classify_request(tabs, system_text); r["max_tokens"] = 8000
            reqs2.append(r); metas2.append({"ids": [tb["table_id"] for tb in chunk], "slots": ["r2_classify"]})
        _, st2 = LBC.run_batches(reqs2, metas2, make_rows, f"{out_prefix}_classify_log2.parquet", HAIKU, max_concurrency=max_concurrency)
        stats["tokens"] += st2["tokens"]; stats["requests"] += st2["requests"]
    json.dump({tb["table_id"]: dict(study=tb["study_accession"], pmcid=tb["pmcid"], file=tb["file"], sheet=("" if pd.isna(tb["sheet"]) else str(tb["sheet"])), columns=classified.get(tb["table_id"], [])) for tb in tables_ok}, open(f"{out_prefix}_classified_columns.json", "w"))
    rel = worklist.drop_duplicates(["pmcid", "study_accession"]).set_index(["pmcid", "study_accession"]).relation.to_dict()
    det_all = extract(tables_ok, classified, rel)
    det = select_best(det_all)
    return det, mapdf, stats, det_all


def extract(tables_ok, classified, relation_lookup=None):
    """Stage 3: deterministic extraction of classified columns for mapped rows. relation_lookup: {(pmcid, study): relation}."""
    rows = []
    for tb in tables_ok:
        cols = classified.get(tb["table_id"], [])
        hdr, body = tb["hdr"], tb["body"]
        subject_level = ":subject" in (tb["method"] or "")
        for c in cols:
            f = c.get("field")
            if f not in FIELDS or f == "none":
                continue
            if c.get("header") not in hdr:
                continue
            if subject_level and f not in STATIC:
                continue
            j = hdr.index(c["header"])
            if j == tb["id_col"] and f not in ("subject_id", "timepoint_label"):
                continue
            legend = {str(l.get("raw", "")).strip().lower(): l.get("normalized") for l in (c.get("legend") or []) if l.get("normalized") in VOCAB.get(f, {"yes", "no"}) or f in ("age_at_collection_days",)}
            legend = {k: v for k, v in legend.items() if f not in ("age_at_collection_days",)}  # legends only for categorical
            unit = c.get("unit") if c.get("unit") not in (None, "none") else None
            for ri, sk in tb["hits"].items():
                raw = body[ri][j] if j < len(body[ri]) else None
                val, note = normalize(f, raw, unit, legend, c["header"])
                if val is None:
                    continue
                if f == "age_at_collection_days" and not (0 <= float(val) <= 1100):
                    continue
                if f == "gestational_age_weeks" and not (20 <= float(val) <= 45):
                    continue
                targets = sk if isinstance(sk, list) else [sk]
                for tk in targets:
                    rows.append(dict(sample_key=tk, study_accession=tb["study_accession"], field_name=f, field_value=str(raw)[:120], value_normalized=str(val),
                                     confidence=(0.85 if not subject_level else 0.75) - (0.1 if tb.get("pooled") else 0.0), evidence_source="paper.supp.table",
                                     evidence_locator=f"{tb['pmcid']}/{tb['file']}/{tb['sheet']}!{c['header']}:{ri + 1}",
                                     evidence_quote=f"{c['header']}={str(raw)[:60]}", determined_by=f"r2_haiku_cols+det_norm", route="R2",
                                     parse_note=f"{note}; map={tb['method']}{'; pooled' if tb.get('pooled') else ''}{'; subject_level_join' if subject_level else ''}", pmcid=tb["pmcid"], paper_id=tb["paper_id"]))
    det = pd.DataFrame(rows)
    if len(det) and relation_lookup is not None:
        det["relation"] = [relation_lookup.get((a, b)) for a, b in zip(det.pmcid, det.study_accession)]
        det["pooled"] = det.parse_note.str.contains("pooled")
    # validator pass on a row-contract projection
    if len(det):
        ok = []
        for r in det.itertuples(index=False):
            row = {"record_id": r.sample_key, "slot": r.field_name, "value": r.value_normalized, "value_unit": "days" if r.field_name == "age_at_collection_days" else None,
                   "outcome": "resolved_from_raw", "confidence": r.confidence, "evidence": [{"source": "paper.supp.table", "quote": " ".join(r.evidence_quote.split()[:12])}], "model": "deterministic+" + HAIKU}
            ok.append(LBC.V["validate_row"](row)[0])
        det = det[np.array(ok)]
    return det


TABLE_RANK = {(True, False): 0, (True, True): 1, (False, False): 2, (False, True): 3}   # (own_data, pooled)


def select_best(det):
    """F3 (pilot): one source table per study x field, ranked own_data>reused and non-pooled>pooled, then coverage;
    per sample take the value from the best-ranked table that has one (no majority vote across tables with different semantics)."""
    if not len(det):
        return det
    d = det.copy()
    d["_tab"] = d.pmcid + "/" + d.evidence_locator.str.split("!").str[0]
    d["_rank"] = [TABLE_RANK[(r == "own_data", bool(p))] for r, p in zip(d.relation, d.pooled)]
    cov = d.groupby(["study_accession", "field_name", "_tab"]).sample_key.nunique().rename("_cov").reset_index()
    d = d.merge(cov, on=["study_accession", "field_name", "_tab"])
    nv = d.groupby(["sample_key", "field_name"]).value_normalized.nunique().rename("n_values_in_route").reset_index()
    # reused pooled tables (rank 3) are independent re-curations of the same deposit: use a majority vote among them
    pooled = d[d._rank == 3]
    if len(pooled):
        maj = pooled.groupby(["sample_key", "field_name", "value_normalized"]).size().rename("_votes").reset_index()
        d = d.merge(maj, on=["sample_key", "field_name", "value_normalized"], how="left")
        d["_votes"] = d["_votes"].fillna(0)
    else:
        d["_votes"] = 0
    d = d.sort_values(["sample_key", "field_name", "_rank", "_votes", "_cov", "confidence"], ascending=[True, True, True, False, False, False])
    best = d.drop_duplicates(["sample_key", "field_name"]).drop(columns=["_tab", "_rank", "_cov", "_votes"])
    return best.merge(nv, on=["sample_key", "field_name"], how="left")

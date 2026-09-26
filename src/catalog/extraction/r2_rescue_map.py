"""R2 rescue: extended ID gate on top of r2_supp_extract.map_ids.

Methods, tried in this order per table column (original methods first):
  orig        : r2_supp_extract.map_ids (accession / library_name / sample_title / subject_id_raw)
  attr_exact  : (a) exact match against ANY attribute value of the study's samples (inverted index)
  attr_norm   : (b) casefold / alnum / alnum_lz match against the same index + sample_title/library_name/alias
  composite   : (c) subject column + timepoint/visit/date column joined on an attribute pair
  subject     : (d) IDs match a non-unique attribute (subject id) -> subject-level join (static fields only)
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
import re, math
import pandas as pd, numpy as np
import r2_supp_extract as R2
import r1_parsers as RP

NORMS = R2.NORMS  # exact, casefold, alnum, alnum_lz
NORM_FN = dict(NORMS)

ID_LIKE = re.compile(r"subject|participant|individual|patient|infant|child|baby|host_id|donor|family|mother|twin|pair|person|volunteer|kid|neonate|newborn|_id$|^id$|\bid\b|identifier|name|alias|code|barcode|label|sample|specimen|library|tube|isolate|strain|title", re.I)
BLACKLIST = re.compile(r"^(tax_id|scientific_name|organism|center_name|ena_.*|checklist|ena_checklist|project_name|biosamplemodel|ncbi_submission_package|insdc_.*|bioproject|study.*|sex|gender|country|geo_loc_name|body_site|host|host_tax_id|host_taxid|host_scientific_name|sample_type|isolation_source|env_.*|lat_lon|description|host_age|age|host_age_unit|.*age.*|.*weight.*|.*delivery.*|.*feeding.*|.*antibiotic.*|.*gestation.*|collection_date|.*date.*|sample_name_taxon_id|sample_name_scientific_name|broker_name|investigation_type|sequencing_method|library_.*|instrument.*|platform|status|host_status|disease|phenotype|host_phenotype|tissue|material|elevation|depth|altitude|temperature|ph|source_material_id|collected_by|submitted_.*|sra_accession|biosample_accession|first_public|last_update)$", re.I)
ID_LIKE_KEY = re.compile(r"(^|_)id($|_)|identifier|alias|barcode|(^|_)name($|_)|label|(^|_)code($|_)|subject|participant|patient|donor|individual|family|twin|pair|(infant|child|baby|neonate|newborn|kid|mother|host|sample|specimen|library|tube|isolate)_?(id|n|nr|no|num|number|code)($|_)", re.I)
COMP_KEYS = re.compile(r"time|visit|age|day|week|month|date|dol|point|stage|sampling|collection|period|phase", re.I)
SHORT_NUM = re.compile(r"^[-+]?\d+(\.\d+)?$")   # any pure number: not an identifier unless the key name says so
RELATIONAL = re.compile(r"mother|father|partner|sibling|parent|spouse|donor|recipient|match|twin_id|pair_id|maternal|paternal", re.I)
STATIC = R2.STATIC


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
    variants = [("", clean), ("affix_", R2._strip_affix(clean))]
    aln = idx["levels"]["alnum"]
    for vname, vals in variants:
        # numeric test on the variant actually matched: "30 min" -> affix-stripped "30" is a bare number
        col_numeric = sum(1 for i in nz if SHORT_NUM.match(str(vals[i]))) >= 0.9 * len(nz)
        ov = len({R2._n_alnum(vals[i]) for i in nz} & set(aln))
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
                    pool.setdefault("alnum_lz", set()).add(R2._n_lz(v)); pool.setdefault("casefold", set()).add(R2._n_case(v))
                    pool.setdefault("digits", set()).add(_digits(v))
                    dn = _date_norm(v)
                    if dn: pool.setdefault("date", set()).add(dn)
    for j in range(min(ncols, 60)):
        if j in exclude_cols:
            continue
        col = [body[r][j] if j < len(body[r]) else None for r in rows]
        if sum(1 for c in col if c not in (None, "")) < 3:
            continue
        for lname, fn in [("casefold", R2._n_case), ("alnum_lz", R2._n_lz), ("date", _date_norm), ("digits", _digits)]:
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
        method, hits, rate, n = R2.map_ids(cols[j], base_levels)
        if method:
            # bare-number columns (and any subject-level match) must sit under an identifier-like header, not a count/statistic
            _cl, _nz = _clean_ids(cols[j])
            _vals = R2._strip_affix(_cl) if method.startswith("affix_") else _cl   # test the variant that matched
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

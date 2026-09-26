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
# expects in namespace: WL, STUDIES, samples, runs, SA, R2, RM, pd, time, os, json
import pickle, traceback
LOG = open("rescue_progress.log", "a")
def log(msg):
    LOG.write(f"{time.strftime('%H:%M:%S')} {msg}\n"); LOG.flush()

if "mapping_rows" not in dir():
    mapping_rows, tables_ok, done_studies = [], [], set()
read_cache = {}
order_studies = [s for s in STUDIES if s not in done_studies]
t_start = time.time()
for si, st in enumerate(order_studies):
    try:
        idx = RM.build_attr_index(st, samples, SA)
        base = R2.study_keys(st, samples, runs)
    except Exception as e:
        log(f"{st} index error {type(e).__name__}: {e}"); done_studies.add(st); continue
    w = WL[WL.study_accession.eq(st)]
    n_ok = 0
    for t in w.itertuples(index=False):
        rec = dict(study_accession=st, pmcid=t.pmcid, paper_id=t.paper_id, relation=t.relation, file=t.file, sheet=("" if pd.isna(t.sheet) else str(t.sheet)),
                   n_rows=None, id_col=None, method=None, matched_attr_key=None, n_ids=0, n_mapped=0, match_rate=0.0, status=None, accepted=False)
        if t.already_accepted:
            rec["status"] = "already_accepted_pilot"; mapping_rows.append(rec); continue
        if (t.n_rows or 0) > 60000:
            rec["status"] = "too_large"; mapping_rows.append(rec); continue
        zp = f"supp_zips/{t.pmcid}.zip"
        if not os.path.exists(zp):
            rec["status"] = "zip_missing"; mapping_rows.append(rec); continue
        ck = (t.pmcid, t.file, rec["sheet"])
        try:
            if ck not in read_cache:
                read_cache[ck] = R2.read_table(zp, t.file, t.sheet if not pd.isna(t.sheet) else None, int(t.header_row_index or 0))
            hdr, body, err = read_cache[ck]
        except Exception as e:
            hdr, body, err = None, None, f"read_error:{type(e).__name__}"
        if err:
            rec["status"] = err; mapping_rows.append(rec); continue
        rec["n_rows"] = len(body)
        if len(body) > 60000:
            rec["status"] = "too_large"; mapping_rows.append(rec); continue
        try:
            att = RM.map_table(hdr, body, t.sid_col if isinstance(t.sid_col, str) else None, base, idx)
            b = RM.choose(att)
        except Exception as e:
            rec["status"] = f"map_error:{type(e).__name__}"; log(f"{st} {t.file} {t.sheet} map_error {traceback.format_exc()[-300:]}"); mapping_rows.append(rec); continue
        if b is None:
            rec["status"] = "no_match"; mapping_rows.append(rec); continue
        rec.update(id_col=hdr[b["col"]], method=b["method"], matched_attr_key=b["matched_attr_key"], n_ids=b["n"], n_mapped=len(b["hits"]), match_rate=round(b["rate"], 3), status=b["status"], accepted=b["status"].startswith("mapped"))
        mapping_rows.append(rec)
        if rec["accepted"]:
            n_ok += 1
            tables_ok.append(dict(table_id=f"R{len(tables_ok)}", study_accession=st, pmcid=t.pmcid, paper_id=t.paper_id, file=t.file, sheet=rec["sheet"], hdr=hdr, body=body,
                                  id_col=b["col"], hits=b["hits"], method=b["method"], sid_header=hdr[b["col"]], pooled=b["pooled"], matched_attr_key=b["matched_attr_key"], stage=b["stage"]))
    done_studies.add(st)
    read_cache.clear()
    log(f"[{si+1}/{len(order_studies)}] {st} tables={len(w)} accepted={n_ok} elapsed={time.time()-t_start:.0f}s")
    if (si + 1) % 15 == 0 or si + 1 == len(order_studies):
        pd.DataFrame(mapping_rows).to_csv("rescue_table_mapping.csv", index=False)
        json.dump(sorted(done_studies), open("handoff/done_studies.json", "w"))
        log(f"checkpoint: {len(mapping_rows)} mapping rows, {len(tables_ok)} accepted tables")
LOG.close()

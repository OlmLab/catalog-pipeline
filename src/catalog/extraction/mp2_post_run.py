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
# Post-processing for multi-paper pass 2. Expects in namespace: sts_all (raw statements list from DRV.run_requests, all waves),
# samples, sd, r1det, descs, host, LBC, R3, DRV, MP, OPUS, pd, np, json, time
import importlib; importlib.reload(MP)
uni = DRV.union_statements(sts_all)
n_valid = sum(bool(s.get("_valid")) for s in sts_all)
print("valid stmts", n_valid, "unique after union", len(uni), "in both reps", sum(len(s["_reps"])==2 for s in uni))
for i,s in enumerate(uni): s["stmt_id"]=f"S{i:03d}"; s["_flags"]=MP.rule_flags(s)
fl = pd.Series([f for s in uni for f in s["_flags"]]).value_counts(); print("rule flags:", fl.to_dict())
passing = [s for s in uni if not s["_flags"]]
print("passing rules:", len(passing), "fields:", pd.Series([s["field"] for s in passing]).value_counts().to_dict())
print("applies_to types:", pd.Series([(s.get("applies_to") or {}).get("type") for s in passing]).value_counts().to_dict())
# expansion (one statement at a time to keep stmt_id)
dets=[]
for s in passing:
    if s["field"]=="age_attribute_unit": continue
    d = R3.expand([s], s["_study"], samples, r1det)
    if len(d): d["stmt_id"]=s["stmt_id"]; dets.append(d)
det = pd.concat(dets, ignore_index=True) if dets else pd.DataFrame(columns=["sample_key","study_accession","field_name","value_normalized","stmt_id","parse_note","confidence"])
print("expanded rows", len(det), "statements expanded", det.stmt_id.nunique() if len(det) else 0)
ex12 = sd[sd.route.isin(["R1","R2"])]
if len(det):
    det_c, cons = MP.consistency_check(det, ex12)
else:
    det_c, cons = det.copy(), pd.DataFrame(columns=["stmt_id","n_rows","n_overlap","n_agree","disagree_frac","drop"])
print("consistency drops:", int(cons["drop"].sum()) if len(cons) else 0)
if len(cons): print(cons[cons.n_overlap>0].to_string())
k12 = set(zip(ex12.sample_key, ex12.field_name))
ex34 = sd[sd.route.isin(["R3","R4"])]; k34 = set(zip(ex34.sample_key, ex34.field_name))
det_c["_k"]=list(zip(det_c.sample_key, det_c.field_name))
det_g = det_c[~det_c._k.isin(k12)].copy()
det_g["parse_note"] = np.where(det_g._k.isin(k34), "supersedes_existing_R3R4", det_g.parse_note)
print("rows after R1/R2 gap restriction", len(det_g), "supersede R3/R4:", int((det_g.parse_note=="supersedes_existing_R3R4").sum()), "statements alive", det_g.stmt_id.nunique(), "studies", det_g.study_accession.nunique())
if len(det_g): print(det_g.groupby("field_name").agg(rows=("sample_key","size"), stmts=("stmt_id","nunique")).to_string())
alive = {s["stmt_id"]:s for s in passing if s["stmt_id"] in set(det_g.stmt_id)}
nscope = det_g.groupby("stmt_id").sample_key.nunique() if len(det_g) else pd.Series(dtype=int)
aud_in=[]
for sid,s in alive.items():
    aud_in.append(dict(stmt_id=sid, study=s["_study"], ena_title=descs.get(s["_study"],("",""))[0][:80], pmcid=s["_pmcid"], relation=s["_relation"], field=s["field"],
                       value_normalized=s["value_normalized"], value_raw=s.get("value_raw"), quote=s["quote"], section=s.get("section"), applies_to=s.get("applies_to"), note=(s.get("note") or "")[:150], n_samples_in_scope=int(nscope[sid])))
for a in aud_in: print(a["stmt_id"], a["study"], a["relation"][:5], a["field"], a["value_normalized"], "|", a["quote"], "|", json.dumps(a["applies_to"])[:60], a["n_samples_in_scope"])

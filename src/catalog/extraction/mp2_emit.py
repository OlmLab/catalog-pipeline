# Emission after Opus audit. Expects: verd (dict stmt_id->verdict), aud_in, det_g, uni, passing, cons, sts_all, sel_all (units read), alll, paper_status, nsamp, studies, stmts, LBC, R3, pd, np, json
audit_rows=[]
for a in aud_in:
    v=verd.get(a["stmt_id"], {"verdict":"missing","reason":"no verdict returned"})
    audit_rows.append(dict(**{k:(json.dumps(a[k]) if k=="applies_to" else a[k]) for k in a}, verdict=v["verdict"], reason=" ".join(str(v["reason"]).split()[:20])))
audit_df=pd.DataFrame(audit_rows); audit_df.to_csv("out/r3_multipaper2_statement_audit.csv", index=False)
keep_ids={s for s,v in verd.items() if v["verdict"]=="keep"}; down_ids={s for s,v in verd.items() if v["verdict"]=="downgrade"}; drop_ids={s for s,v in verd.items() if v["verdict"]=="drop"}
final = det_g[det_g.stmt_id.isin(keep_ids|down_ids)].copy()
final["group_audit"]=final.stmt_id.map(lambda s: "opus_keep" if s in keep_ids else "opus_downgrade")
final.loc[final.stmt_id.isin(down_ids), "confidence"] = (final.loc[final.stmt_id.isin(down_ids), "confidence"]*0.5).clip(upper=0.5)
final = final.sort_values(["confidence"], ascending=False).drop_duplicates(["sample_key","field_name"])
final["evidence_limited_to_abstract"]=0
final["determined_by"]="r3_multipaper_sonnet_group"
schema_cols=['sample_key','study_accession','field_name','field_value','value_normalized','confidence','evidence_source','evidence_locator','evidence_quote','evidence_limited_to_abstract','determined_by','route','scope','parse_note','group_audit','stmt_id','pmcid','applies_to']
final=final[schema_cols].reset_index(drop=True)
rej=[]; okmask=[]
for r in final.itertuples(index=False):
    row={"record_id":r.sample_key,"slot":r.field_name,"value":r.value_normalized,"value_unit":"days" if r.field_name=="age_at_collection_days" else None,"outcome":"predicted","confidence":float(r.confidence),"model":R3.SONNET,
         "evidence":[{"source":r.evidence_source,"quote":r.evidence_quote}]}
    ok,msg=LBC.V["validate_row"](row); okmask.append(ok)
    if not ok: rej.append(dict(r._asdict(), reject_reason=msg))
final_ok=final[okmask].reset_index(drop=True)
print("final rows", len(final_ok), "row-level rejects", len(rej), "samples", final_ok.sample_key.nunique(), "studies", final_ok.study_accession.nunique())
if len(final_ok):
    print(final_ok.groupby(["field_name","group_audit"]).size().to_string())
    print(final_ok.groupby("study_accession").agg(rows=("sample_key","size"), samples=("sample_key","nunique"), fields=("field_name", lambda x: ",".join(sorted(set(x))))).to_string())
alive_set=set(alive); cons_drop=set(cons[cons["drop"]].stmt_id) if len(cons) else set()
def status_of(s):
    sid=s["stmt_id"]
    if s["_flags"]: return "rule_dropped:"+";".join(s["_flags"])
    if s["field"]=="age_attribute_unit": return "recorded_only_unit_hint"
    if sid in cons_drop: return "consistency_dropped"
    if sid not in alive_set: return "no_new_pairs_or_unexpandable"
    return "audit_"+verd.get(sid,{"verdict":"missing"})["verdict"]
st_rows=[]
for s in uni:
    st_rows.append(dict(stmt_id=s["stmt_id"], study_accession=s["_study"], pmcid=s["_pmcid"], relation=s["_relation"], chunk=s["_chunk"], replicates=len(s["_reps"]), field=s["field"], value_normalized=s["value_normalized"], value_raw=s.get("value_raw"),
                        applies_to=json.dumps(s.get("applies_to")), quote=s.get("quote"), section=s.get("section"), confidence=s.get("confidence"), note=s.get("note"), rule_flags=";".join(s["_flags"]), status=status_of(s),
                        audit_reason=verd.get(s["stmt_id"],{}).get("reason"), rows_emitted=int((final_ok.stmt_id==s["stmt_id"]).sum())))
stmts_df=pd.DataFrame(st_rows)
inval=[s for s in sts_all if not s.get("_valid")]
rej_rows=[dict(study_accession=s["_study"], pmcid=s["_pmcid"], field=s.get("field"), value_normalized=s.get("value_normalized"), applies_to=json.dumps(s.get("applies_to")), quote=str(s.get("quote")), reject_stage="validator", reject_reason=str(s["_row"].get("note"))) for s in inval]
for r in stmts_df[stmts_df.status.str.startswith(("rule_dropped","consistency","audit_drop"))].itertuples():
    rej_rows.append(dict(study_accession=r.study_accession, pmcid=r.pmcid, field=r.field, value_normalized=r.value_normalized, applies_to=r.applies_to, quote=r.quote, reject_stage=r.status.split(":")[0], reject_reason=(r.rule_flags or r.audit_reason or "consistency >20% disagreement on >=5 overlapping samples")))
rej_df=pd.DataFrame(rej_rows+[dict(study_accession=x["study_accession"],pmcid=x["pmcid"],field=x["field_name"],value_normalized=x["value_normalized"],applies_to=x["applies_to"],quote=x["evidence_quote"],reject_stage="row_validator",reject_reason=x["reject_reason"]) for x in rej])
print("statements", len(stmts_df), stmts_df.status.value_counts().to_dict()); print("rejected", len(rej_df), rej_df.reject_stage.value_counts().to_dict() if len(rej_df) else {})
final_ok.to_parquet("out/r3_multipaper2_determinations.parquet", index=False)
stmts_df.to_parquet("out/r3_multipaper2_statements.parquet", index=False)
rej_df.to_parquet("out/r3_multipaper2_rejected.parquet", index=False)
read_units = sel_all[sel_all.kind=="fulltext"]
rows=[]
for s in studies:
    lk=alll[alll.study_accession==s]; ru=read_units[read_units.study==s]
    pw=[p for p in lk.pmcid.dropna() if paper_status.get(p)!="ok"]
    st=stmts_df[stmts_df.study_accession==s]; fin=final_ok[final_ok.study_accession==s]
    if len(ru)==0: status="not_read_this_track (token budget)" if len(lk[~lk.already_read])>0 or len(lk)>0 else "no_unread_units"
    elif len(st)==0: status="read_no_group_statements"
    elif len(fin)==0: status="read_statements_no_new_rows"
    else: status="ok_new_rows"
    rows.append(dict(study_accession=s, n_infant_samples=int(nsamp.get(s,0)), n_linked_papers=len(lk), n_fulltext_ok=int(lk.pmcid.map(lambda p: paper_status.get(p)=="ok").sum()),
                     papers_read_before=int(lk.already_read.sum()), units_read_this_track=len(ru), papers_read_this_track=ru.pmcid.nunique(),
                     papers_this_track=";".join(f"{p}({r[:5]},c{c})" for p,r,c in ru[["pmcid","relation","chunk"]].itertuples(index=False)),
                     paywalled_or_no_fulltext=";".join(pw),
                     statements_unique=len(st), statements_pass_rules=int((~st.status.str.startswith("rule_dropped")).sum()) if len(st) else 0, statements_kept_after_audit=int(st.status.isin(["audit_keep","audit_downgrade"]).sum()) if len(st) else 0,
                     rows_gained=len(fin), samples_gained=fin.sample_key.nunique(), fields_gained=",".join(sorted(fin.field_name.unique())), status=status))
per_study=pd.DataFrame(rows); per_study.to_csv("out/r3_multipaper2_per_study.csv", index=False)
print(per_study.status.value_counts().to_dict())

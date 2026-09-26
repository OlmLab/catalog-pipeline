out=[]
for sa in studies.study_accession:
    oc=st.at[sa,'outcome']; ns=int(st.at[sa,'n_samples'])
    lp=lk[lk.study_accession==sa].sort_values(['rel_rank','confidence'],ascending=[True,False])
    for f in FIELDS:
        row=dict(study_accession=sa,outcome=oc,n_samples=ns,field=f,tier=None,evidence=None,source_paper_id=None,source_file=None,confidence=None,note=None)
        rr=r1i.loc[(sa,f)] if (sa,f) in r1i.index else None
        if rr is not None and rr.hit_frac>=0.5:
            row.update(tier='R1',confidence=round(min(0.95,0.6+rr.hit_frac*0.35),2),
                evidence=json.dumps([{"source":f"sample.attr.{rr.attr_col}","quote":" ".join(str(rr.example).split()[:12])}]),note=f"hit_frac={rr.hit_frac:.2f};attr_col={rr.attr_col}")
            out.append(row); continue
        hit=None
        for p in lp.itertuples():
            if (p.pmcid,f) in paper_field_tab:
                fl,sh,col,nr=max(paper_field_tab[(p.pmcid,f)],key=lambda x:x[3]); hit=(p,fl,sh,col,nr); break
        if hit:
            p,fl,sh,col,nr=hit
            row.update(tier='R2',source_paper_id=str(p.paper_id),source_file=fl,confidence=0.8 if p.relation=='own_data' else 0.6,
                evidence=json.dumps([{"source":f"paper.supp.{fl}[{sh}!{col[:60]}]","quote":" ".join(col.split()[:12])}]),note=f"relation={p.relation};n_rows={nr}")
            out.append(row); continue
        hit=None
        for p in lp.itertuples():
            if p.pmcid in xs.index and xs.at[p.pmcid,f+'_n']>0:
                hit=p; break
        if hit is not None:
            q=str(xs.at[hit.pmcid,f+'_quote']); srcl=xs.at[hit.pmcid,f+'_src']
            row.update(tier='R3',source_paper_id=str(hit.paper_id),confidence=0.5 if hit.relation=='own_data' else 0.4,
                evidence=json.dumps([{"source":srcl,"quote":" ".join(q.split()[:12])}]),note=f"relation={hit.relation};n_mentions={int(xs.at[hit.pmcid,f+'_n'])}")
            out.append(row); continue
        if rr is not None and rr.hit_frac>0:
            row.update(tier='R3',confidence=0.4,evidence=json.dumps([{"source":f"sample.attr.{rr.attr_col}","quote":" ".join(str(rr.example).split()[:12])}]),note=f"partial_attr hit_frac={rr.hit_frac:.2f}")
            out.append(row); continue
        if len(lp)>0 and not lp.has_xml.any():
            p=lp.iloc[0]
            row.update(tier='R4',source_paper_id=str(p.paper_id),confidence=0.3,evidence=json.dumps([{"source":"paper.abstract","quote":"full text not cached; abstract only"}]),note="evidence_limited_to=abstract")
            out.append(row); continue
        if len(lp)>0:
            row.update(tier='R0',confidence=0.5,evidence=json.dumps([]),note=f"fulltext_scanned_no_mention;n_papers={len(lp)}")
        else:
            row.update(tier='R0',confidence=0.5,evidence=json.dumps([]),note="no_linked_paper;no_attribute")
        out.append(row)
rec=pd.DataFrame(out)

def run_det():
    out=[]; unparsed=[]
    def emit(sk,key,field,raw,norm,conf,note,det='deterministic_r1'):
        out.append(dict(sample_key=sk,field_name=field,field_value=raw,value_normalized=norm,confidence=conf,evidence_locator=key,
                        evidence_quote=' '.join(str(raw).split()[:12])[:200],determined_by=det,parse_note=note))
    for _,m in fm[fm.parser!='haiku'].iterrows():
        key,field,parser,unit,conf=m.attr_key_norm,m.field_name,m.parser,m.unit_default,m.confidence
        unit=None if (unit is None or (isinstance(unit,float) and np.isnan(unit))) else unit
        sub=A_[A_.attr_key_norm==key]
        if parser=='age_text_unitkey':
            for sk,v in zip(sub.sample_key,sub.attr_value):
                s=str(v).strip()
                if P.is_null(s): continue
                if re.fullmatch(P.NUM,s):
                    u=unit_for(sk,key) or unit
                    if u is None: emit(sk,key,field,v,None,conf,'bare number, no unit key'); unparsed.append((key,field,s,'bare_no_unit')); continue
                    d=P.to_days(float(s),u); emit(sk,key,field,v,None if d is None else round(d),conf,f'unit_key {u}')
                else:
                    d,note=P.parse_age_text(s); emit(sk,key,field,v,d,conf,note)
                    if d is None: unparsed.append((key,field,s,note))
                    if re.search(r'pre-?term|prematur',s,re.I): emit(sk,key,'preterm_status',v,'preterm',0.85,'age text says premature')
            continue
        dist=sub.attr_value.drop_duplicates(); res={}
        for v in dist:
            if parser=='age_numeric': res[v]=P.parse_age_numeric(v,unit)
            elif parser=='age_text': res[v]=P.parse_age_text(v)
            elif parser=='babyid_dol':
                mm=re.fullmatch(r'([A-Za-z]+\d+)_(\d+)',str(v)); res[v]=((int(mm.group(2)),'babyid_dol') if field=='age_at_collection_days' else (mm.group(1),'babyid')) if mm else (None,'unparsed')
            elif parser=='phenotype_age_sex':
                mm=re.match(r'(female|male)_subject_of_(\d+(?:\.\d+)?)_years',str(v))
                res[v]=((round(float(mm.group(2))*365.25),'phenotype') if mm else (None,'unparsed')) if field=='age_at_collection_days' else P.parse_sex(v,key)
            elif parser in('ga_numeric','ga_wplusd'): res[v]=P.parse_ga(v,unit)
            elif parser=='bw_numeric': res[v]=P.parse_bw(v)
            elif parser=='categorical_delivery': res[v]=P.parse_delivery(v,key)
            elif parser=='categorical_feeding': res[v]=P.parse_feeding(v,key)
            elif parser=='percent_feeding': res[v]=P.parse_percent_feeding(v,key)
            elif parser=='categorical_yesno': res[v]=P.parse_yesno(v,key)
            elif parser=='categorical_sex': res[v]=P.parse_sex(v,key)
            elif parser=='categorical_nec': res[v]=P.parse_nec(v,key)
            elif parser=='categorical_hmo': res[v]=P.parse_hmo(v,key)
            elif parser=='categorical_probiotic_freq': res[v]=P.parse_probiotic_freq(v,key)
            elif parser=='categorical': res[v]=P.parse_preterm_coded(v,key)
            elif parser=='country': res[v]=P.parse_country(v)
            elif parser in ('identifier','label'): res[v]=(None,'null') if P.is_null(v) else (str(v).strip(),parser)
            else: res[v]=(None,'no parser')
        for sk,v in zip(sub.sample_key,sub.attr_value):
            norm,note=res[v]
            if note=='null': continue
            emit(sk,key,field,v,norm,conf,note)
            if norm is None: unparsed.append((key,field,str(v),note))
    d=pd.DataFrame(out); d['study_accession']=d.sample_key.map(s2study)
    u=pd.DataFrame(unparsed,columns=['attr_key_norm','field_name','value','note']).drop_duplicates()
    return d,u

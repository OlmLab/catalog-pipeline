"""R2 track 'PDF/DOCX supplements': table extraction from supplementary PDF / DOCX / mis-typed XLSX
members of Europe PMC supplementary ZIPs, then the UNCHANGED r2_supp_extract gate (map_ids), extended
with an exact-match inverted index over the study's BioSample attribute values.
"""
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
import os, re, io, json, zipfile, sqlite3, time
import pandas as pd, numpy as np
import supp_parse as SP
import r2_supp_extract as R2

ZIP_DIR = "supp_zips"
SUBJECT_ATTR_RX = re.compile(r"subject|infant|participant|individual|patient|child|baby|host_id|donor|family|mother|twin|pair", re.I)
ATTR_DENY_RX = re.compile(r"date|time|lat|lon|geo|env|biome|feature|material|medium|age|weight|height|length|bmi|temperature|ph$|depth|elev|isolation_source|description|title|model|platform|strategy|source|selection|layout|count|bases|size|reads|url|md5|checksum|type$|note|comment", re.I)


# ------------------------------------------------------------------ ZIP acquisition
def get_zip(pmcid, cache_db, blob_root, HL, log):
    """Return local zip path or None. Order: local copy -> harvest cache blob -> harvest_lib fetch (<=30 s, 2 tries)."""
    os.makedirs(ZIP_DIR, exist_ok=True)
    p = os.path.join(ZIP_DIR, f"{pmcid}.zip")
    if os.path.exists(p) and os.path.getsize(p) > 100:
        return p
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/supplementaryFiles"
    if cache_db and os.path.exists(cache_db):
        try:
            con = sqlite3.connect(cache_db)
            row = con.execute("SELECT status, blob_sha FROM http_cache WHERE url=?", (url,)).fetchone()
            con.close()
        except Exception as e:
            row = None; log.append((pmcid, f"cache_db_error:{e}"))
        if row and row[0] == 200 and row[1]:
            bp = os.path.join(blob_root, row[1][:2], row[1])
            if os.path.exists(bp) and os.path.getsize(bp) > 100:
                b = open(bp, "rb").read()
                if b[:2] == b"PK":
                    open(p, "wb").write(b); return p
                log.append((pmcid, "cache_blob_not_zip"))
            else:
                log.append((pmcid, "cache_blob_missing"))
    if HL is None:
        return None
    for attempt in range(2):
        try:
            r = HL.fetch(url, purpose="r2_pdfdocx_suppl", timeout=30, expect="bytes")
            if r.get("ok") and r.get("body") and r["body"][:2] == b"PK":
                open(p, "wb").write(r["body"]); return p
            log.append((pmcid, f"fetch_status_{r.get('status')}"))
            if r.get("status") in (404, 500):
                break
        except Exception as e:
            log.append((pmcid, f"fetch_error:{type(e).__name__}"))
    return None


def member_bytes(zp, member):
    parts = member.split("::")
    with zipfile.ZipFile(zp) as z:
        b = z.read(parts[0])
    for q in parts[1:]:
        with zipfile.ZipFile(io.BytesIO(b)) as z:
            b = z.read(q)
    return b


# ------------------------------------------------------------------ table extraction
def _norm_rows(rows):
    rows = [[("" if c is None else str(c)).replace("\n", " ").strip() for c in r] for r in rows if r]
    return [r for r in rows if sum(1 for c in r if c) >= 2]


def tables_from_docx(b):
    """[(sheet, rows)] via python-docx (merged cells repeat their text; we keep them)."""
    import docx
    doc = docx.Document(io.BytesIO(b))
    out = []
    for ti, tbl in enumerate(doc.tables):
        rows = []
        for tr in tbl.rows:
            cells = []
            try:
                for tc in tr.cells:
                    cells.append(tc.text)
            except Exception:
                cells = [tc.text for tc in tr._tr.tc_lst] if hasattr(tr._tr, "tc_lst") else []
            # collapse horizontally merged duplicates (python-docx repeats the same cell object)
            dedup = []
            for c in cells:
                if not dedup or c != dedup[-1] or c == "":
                    dedup.append(c)
            rows.append(dedup)
        rows = _norm_rows(rows)
        if len(rows) >= 2:
            out.append((f"table{ti+1}", rows))
    return out


def _text_table(txt):
    """Fallback: lines with >=3 tokens split on 2+ spaces / tabs, keep the dominant column count +-1."""
    lines = []
    for ln in txt.splitlines():
        parts = [p for p in re.split(r"\t|\s{2,}", ln.strip()) if p]
        if len(parts) >= 3:
            lines.append(parts)
    if len(lines) < 5:
        return None
    w = pd.Series([len(l) for l in lines]).mode().iloc[0]
    keep = [l for l in lines if abs(len(l) - w) <= 1]
    return keep if len(keep) >= 5 else None


def tables_from_pdf(b, max_pages=60):
    """[(sheet, rows)], status. pdfplumber tables across pages; same-header tables spanning pages are
    concatenated; if no table anywhere, try camelot (stream) then a text-layout fallback.
    Scanned PDFs (no extractable text on any page) -> status 'scanned_pdf'."""
    import pdfplumber
    out, any_text, status = [], False, "ok"
    try:
        pdf = pdfplumber.open(io.BytesIO(b))
    except Exception as e:
        return [], f"pdf_open_error:{type(e).__name__}"
    try:
        n = min(len(pdf.pages), max_pages)
        for pi in range(n):
            page = pdf.pages[pi]
            try:
                txt = page.extract_text() or ""
            except Exception:
                txt = ""
            if txt.strip():
                any_text = True
            try:
                tables = page.extract_tables()
            except Exception:
                tables = []
            got = False
            for ti, tbl in enumerate(tables[:6]):
                rows = _norm_rows(tbl)
                if len(rows) >= 2 and max(len(r) for r in rows) >= 3:
                    out.append((f"page{pi+1}_t{ti+1}", rows)); got = True
            if not got and txt.strip():
                tt = _text_table(txt)
                if tt:
                    out.append((f"page{pi+1}_txt", tt))
        if len(pdf.pages) > max_pages:
            status = f"truncated_{max_pages}_of_{len(pdf.pages)}_pages"
    finally:
        pdf.close()
    if not any_text:
        return [], "scanned_pdf"
    if not out:
        try:
            import camelot, tempfile
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                f.write(b); tmp = f.name
            tl = camelot.read_pdf(tmp, pages="1-%d" % min(n, 30), flavor="stream")
            for i, t in enumerate(tl):
                rows = _norm_rows(t.df.values.tolist())
                if len(rows) >= 2:
                    out.append((f"camelot_t{i+1}", rows))
            os.unlink(tmp)
            if out:
                status = "camelot_stream"
        except Exception as e:
            status = f"no_tables;camelot_{type(e).__name__}"
    return out, status


def stitch_pdf_tables(tabs):
    """Concatenate consecutive page tables that share the same header row (multi-page tables)."""
    if not tabs:
        return tabs
    merged = []
    for sheet, rows in tabs:
        if merged and re.match(r"page\d+_t1$", sheet) and re.match(r"page\d+_t\d+$", merged[-1][0].split("+")[0]):
            prev_sheet, prev_rows = merged[-1]
            h_prev = [c.lower() for c in prev_rows[0]]
            h_cur = [c.lower() for c in rows[0]]
            if len(h_prev) == len(h_cur) and (h_prev == h_cur):
                merged[-1] = (prev_sheet + "+" + sheet, prev_rows + rows[1:])
                continue
            if len(h_prev) == len(rows[0]) and len(prev_rows) > 5 and not any(re.search(r"[a-z]{3,}", c) for c in rows[0][:1]) and sum(1 for c in rows[0] if re.fullmatch(r"[-+]?\d+(\.\d+)?", c)) >= 1:
                # continuation without repeated header: first row already data
                merged[-1] = (prev_sheet + "+" + sheet, prev_rows + rows)
                continue
        merged.append((sheet, rows))
    return merged


def tables_from_notzip_xlsx(b):
    """xlsx members that are not ZIPs: sniff OLE (xls), HTML, or delimited text."""
    if b[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        import xlrd
        wb = xlrd.open_workbook(file_contents=b)
        out = []
        for ws in wb.sheets():
            rows = _norm_rows([ws.row_values(i) for i in range(min(ws.nrows, 200000))])
            if len(rows) >= 2:
                out.append((ws.name, rows))
        return out, "xls_ole"
    head = b[:2000].lstrip().lower()
    if head.startswith(b"<") and (b"<table" in b[:200000].lower() or b"<html" in head):
        dfs = pd.read_html(io.BytesIO(b))
        out = []
        for i, df in enumerate(dfs):
            rows = _norm_rows([list(map(str, df.columns))] + df.astype(str).values.tolist())
            if len(rows) >= 2:
                out.append((f"html{i+1}", rows))
        return out, "html"
    txt = None
    for enc in ("utf-8-sig", "latin-1"):
        try:
            txt = b.decode(enc); break
        except Exception:
            pass
    if txt and txt.count("\n") >= 2:
        import csv
        lines = txt.splitlines()
        h = "\n".join(lines[:20])
        sep = "\t" if h.count("\t") >= h.count(",") and h.count("\t") > 0 else ("," if h.count(",") else ";")
        rows = _norm_rows(list(csv.reader(lines[:200000], delimiter=sep)))
        if len(rows) >= 2:
            return [("text", rows)], "delimited_text"
    return [], "unknown_binary"


def split_header(rows):
    hi = SP.pick_header(rows)
    hdr = [SP._clean(c) if c is not None else "" for c in rows[hi]]
    hdr = [h if h else f"col{i}" for i, h in enumerate(hdr)]
    # de-duplicate headers (extract() uses hdr.index)
    seen = {}
    for i, h in enumerate(hdr):
        if h in seen:
            seen[h] += 1; hdr[i] = f"{h}__{seen[h]}"
        else:
            seen[h] = 0
    body = [[SP._clean(c) if c is not None else None for c in r] + [None] * (len(hdr) - len(r)) for r in rows[hi + 1:]]
    body = [r[:len(hdr)] for r in body if any(c not in (None, "") for c in r)]
    return hi, hdr, body


# ------------------------------------------------------------------ keys: study_keys + attribute inverted index
def attr_keys(study, samples, attrs):
    """Extend R2.study_keys levels with exact (and normalised) matches on BioSample attribute values."""
    smp = samples[samples.study_accession == study]
    a = attrs[attrs.sample_key.isin(set(smp.sample_key))]
    a = a[~a.attr_key_norm.fillna("").str.contains(ATTR_DENY_RX)]
    a = a[a.attr_value.notna()]
    a = a[a.attr_value.astype(str).str.strip().str.len() >= 3]
    a = a[~a.attr_value.astype(str).str.strip().str.lower().isin({"missing", "not collected", "not applicable", "na", "none", "unknown", "not provided", "restricted access"})]
    pairs = []
    for k, v, sk in zip(a.attr_key_norm, a.attr_value.astype(str), a.sample_key):
        kind = "subject" if SUBJECT_ATTR_RX.search(k or "") else "attr"
        pairs.append((v.strip(), sk, kind))
    cnt = pd.Series([p[0] for p in pairs]).value_counts() if pairs else pd.Series(dtype=int)
    # value unique to one sample, or a subject-like key value (may repeat within a subject)
    pairs = [p for p in pairs if (cnt[p[0]] == 1) or (p[2] == "subject" and cnt[p[0]] <= 60)]
    levels = {}
    for name, fn in R2.NORMS:
        d = {}
        for v, k, kind in pairs:
            nv = fn(v)
            if not nv or len(nv) < 3:
                continue
            if kind == "subject":
                d.setdefault(nv, ([], "subject"))
                if isinstance(d[nv][0], list) and k not in d[nv][0]:
                    d[nv][0].append(k)
            elif nv in d and d[nv][0] != k:
                d[nv] = (None, "ambiguous")
            else:
                d.setdefault(nv, (k, "attr"))
        levels[name] = d
    return levels, len(pairs)


def merged_keys(study, samples, runs, attrs):
    base = R2.study_keys(study, samples, runs)
    ext, n_attr = attr_keys(study, samples, attrs)
    for name in ext:
        d = base[name]
        for nv, val in ext[name].items():
            if nv not in d:
                d[nv] = val
    return base, n_attr


# ------------------------------------------------------------------ gate (unchanged thresholds from R2.gate)
def gate_tables(tabs, keys, rel_lookup):
    """tabs: list of dict(study_accession, pmcid, paper_id, file, sheet, hdr, body). Returns (mapping_df, tables_ok)."""
    mapping_rows, tables_ok = [], []
    for t in tabs:
        st, hdr, body = t["study_accession"], t["hdr"], t["body"]
        rec = dict(study_accession=st, pmcid=t["pmcid"], paper_id=t["paper_id"], relation=rel_lookup.get((t["pmcid"], st)), file=t["file"], sheet=t["sheet"],
                   n_rows=len(body), n_cols=len(hdr), id_col=None, method=None, n_ids=0, n_mapped=0, rate=0.0, status=None, member_type=t["member_type"])
        if len(body) < 5:
            rec["status"] = "too_few_rows"; mapping_rows.append(rec); continue
        if len(body) > 60000:
            rec["status"] = "too_large"; mapping_rows.append(rec); continue
        best = (None, None, {}, 0.0, 0)
        for j in range(min(len(hdr), 40)):
            col = [r[j] if j < len(r) else None for r in body]
            method, hits, rate, n = R2.map_ids(col, keys[st])
            if rate > best[3]:
                best = (j, method, hits, rate, n)
            if rate >= 0.95:
                break
        j, method, hits, rate, n = best
        rec.update(id_col=hdr[j] if j is not None else None, method=method, n_ids=n, n_mapped=len(hits), rate=round(rate, 3))
        exact_acc = bool(method) and method.split(":")[0].endswith("exact") and method.endswith((":run", ":sample"))
        if rate >= 0.5 and len(hits) >= 3:
            rec["status"] = "mapped"
        elif exact_acc and len(hits) >= R2.POOLED_MIN:
            rec["status"] = "mapped_pooled"
        else:
            rec["status"] = "below_gate" if len(hits) else "no_match"
        mapping_rows.append(rec)
        if rec["status"].startswith("mapped"):
            tables_ok.append(dict(table_id=f"T{len(tables_ok)}", study_accession=st, pmcid=t["pmcid"], paper_id=t["paper_id"], file=t["file"], sheet=t["sheet"],
                                  hdr=hdr, body=body, id_col=j, hits=hits, method=method, sid_header=hdr[j], pooled=rec["status"] == "mapped_pooled"))
    return pd.DataFrame(mapping_rows), tables_ok


def inventory_row(paper_id, pmcid, member_type, file, sheet, hi, hdr, body, parse_error=None):
    rows = [hdr] + body
    s = SP.summarize([hdr] + body[:SP.N_SAMPLE], file, sheet, n_rows_total=len(rows))
    s.update(paper_id=paper_id, pmcid=pmcid, source_set="R2_pdfdocx_2026-09-25", member_type=member_type, header_row_index=int(hi),
             n_rows=len(body), llm_sid=None, llm_fields=None, llm_model=None, sid_col=None, has_sample_id_final=bool(s["has_sample_id_col"]),
             fields_final_json=s["field_hits"], parse_error=parse_error, pdf_text_head=None)
    return s

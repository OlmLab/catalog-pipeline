"""Deterministic supplement-table inventory: header + first 3 data rows per table-like member."""
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
import io, os, re, zipfile, json, warnings
import pandas as pd
from lxml import etree
warnings.filterwarnings("ignore")

MAX_SHEETS = 50
MAX_COLS = 200
N_SAMPLE = 3
SCAN_ROWS = 40  # rows to scan when looking for the header row

FIELD_RX = {
    "age": re.compile(r"\bage\b|days?_?old|\bmonths?\b|\bweeks?\b|\bdol\b|postnatal|\bpma\b|time_?point|\bvisit\b|\bmonth\b|\bday\b", re.I),
    "delivery": re.compile(r"deliver|birth_?mode|c[- ]?section|cesar|caesar|vaginal|\bborn\b|mode_?of_?birth", re.I),
    "feeding": re.compile(r"feed|breast|formula|\bbf\b|wean|solid|\bmilk", re.I),
    "preterm": re.compile(r"preterm|gestation|\bga\b|premat|birth_?weight|\bbw\b", re.I),
    "antibiotics": re.compile(r"antibio|\babx\b|amox|penicil|cefal|cephal|\btreatment\b|antimicrob", re.I),
    "probiotic": re.compile(r"probiot|lactobac|bifido.*suppl|synbio|supplement", re.I),
}
SAMPLE_ID_RX = re.compile(r"sample|\brun\b|srr|err|drr|biosample|\bsam[ne]|accession|library|barcode|subject|participant|\bid$|_id\b|\bid\b|specimen|patient|infant", re.I)
ACC_VAL_RX = re.compile(r"\b(SRR|ERR|DRR|SAMN|SAMEA|SAMD|SRS|ERS|DRS|SRX|ERX)\d{4,}\b")
TABLE_EXT = {".xlsx", ".xlsm", ".xls", ".csv", ".tsv", ".txt", ".docx", ".pdf", ".ods"}


def _clean(v):
    if v is None:
        return None
    if isinstance(v, float) and v != v:
        return None
    s = str(v).strip()
    return s if s else None


def pick_header(rows):
    """rows: list of lists (strings/None). Choose header row = first row within SCAN_ROWS
    where >=2 non-null cells and fraction of non-null string cells is high and the next row exists."""
    best = None
    for i, r in enumerate(rows[:SCAN_ROWS]):
        cells = [_clean(c) for c in r]
        nn = [c for c in cells if c is not None]
        if len(nn) < 2:
            continue
        str_frac = sum(1 for c in nn if not re.fullmatch(r"[-+]?\d+(\.\d+)?([eE][-+]?\d+)?", c)) / len(nn)
        if str_frac >= 0.6:
            # prefer rows where the following row has similar width
            return i
        if best is None:
            best = i
    return best if best is not None else 0


def summarize(rows, src_file, sheet, n_rows_total=None):
    rows = [list(r) for r in rows if r is not None]
    if not rows:
        return None
    hi = pick_header(rows)
    header = [_clean(c) for c in rows[hi]]
    # trim trailing empty cols
    while header and header[-1] is None:
        header.pop()
    header = header[:MAX_COLS]
    data = [[_clean(c) for c in r[:len(header)]] for r in rows[hi + 1: hi + 1 + N_SAMPLE]]
    ncols = len(header)
    n_rows = (n_rows_total if n_rows_total is not None else len(rows)) - hi - 1
    hdr_txt = [h or "" for h in header]
    field_hits = {}
    for f, rx in FIELD_RX.items():
        cols = [h for h in hdr_txt if h and rx.search(h)]
        if cols:
            field_hits[f] = cols[:6]
    sample_cells = " ".join(str(c) for r in data for c in r if c)
    return dict(
        file=src_file, sheet=sheet, n_rows=int(max(n_rows, 0)), n_cols=int(ncols), header_row_index=int(hi),
        headers=json.dumps(hdr_txt, ensure_ascii=False)[:20000],
        sample_rows=json.dumps(data, ensure_ascii=False)[:20000],
        has_sample_id_col=any(h and SAMPLE_ID_RX.search(h) for h in hdr_txt),
        has_accession_values=bool(ACC_VAL_RX.search(sample_cells)) or bool(ACC_VAL_RX.search(" ".join(hdr_txt))),
        field_hits=json.dumps(field_hits, ensure_ascii=False),
    )


def parse_xlsx(b, name):
    import openpyxl
    out = []
    wb = openpyxl.load_workbook(io.BytesIO(b), read_only=True, data_only=True)
    for ws in wb.worksheets[:MAX_SHEETS]:
        rows = []
        total = 0
        for r in ws.iter_rows(values_only=True):
            total += 1
            if total <= SCAN_ROWS + N_SAMPLE + 2:
                rows.append(r)
        # if header late, we still have SCAN_ROWS+; fine
        s = summarize(rows, name, ws.title, n_rows_total=total)
        if s:
            out.append(s)
    wb.close()
    return out


def parse_xls(b, name):
    import xlrd
    out = []
    wb = xlrd.open_workbook(file_contents=b)
    for ws in wb.sheets()[:MAX_SHEETS]:
        rows = [ws.row_values(i) for i in range(min(ws.nrows, SCAN_ROWS + N_SAMPLE + 2))]
        s = summarize(rows, name, ws.name, n_rows_total=ws.nrows)
        if s:
            out.append(s)
    return out


def parse_delim(b, name):
    txt = None
    for enc in ("utf-8-sig", "latin-1"):
        try:
            txt = b.decode(enc); break
        except Exception:
            continue
    if txt is None:
        return []
    lines = txt.splitlines()
    if len(lines) < 2:
        return []
    head = "\n".join(lines[:20])
    sep = "\t" if head.count("\t") >= head.count(",") and head.count("\t") > 0 else ("," if head.count(",") > 0 else (";" if head.count(";") > 0 else None))
    if sep is None:
        return []
    import csv
    rows = list(csv.reader(lines[:SCAN_ROWS + N_SAMPLE + 2], delimiter=sep))
    s = summarize(rows, name, None, n_rows_total=len(lines))
    return [s] if s else []


W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def parse_docx(b, name):
    out = []
    with zipfile.ZipFile(io.BytesIO(b)) as z:
        if "word/document.xml" not in z.namelist():
            return out
        root = etree.fromstring(z.read("word/document.xml"))
    for ti, tbl in enumerate(root.iter(W + "tbl")):
        if ti >= MAX_SHEETS:
            break
        rows = []
        for tr in tbl.iter(W + "tr"):
            rows.append(["".join(tc.itertext()).strip() for tc in tr.findall(W + "tc")])
        if len(rows) < 2:
            continue
        s = summarize(rows, name, f"table{ti+1}", n_rows_total=len(rows))
        if s:
            out.append(s)
    return out


def _pdf_rows(text):
    """Split page text into lines; keep lines that look tabular (>=3 tokens separated by 2+ spaces or tabs)."""
    lines = []
    for ln in text.splitlines():
        parts = [p for p in re.split(r"\t|\s{2,}", ln.strip()) if p]
        if len(parts) >= 3:
            lines.append(parts)
    return lines


def parse_pdf(b, name, max_pages=12):
    import pdfplumber
    out = []
    try:
        pdf = pdfplumber.open(io.BytesIO(b))
    except Exception:
        return out
    try:
        n = min(len(pdf.pages), max_pages)
        for pi in range(n):
            page = pdf.pages[pi]
            try:
                tables = page.extract_tables()
            except Exception:
                tables = []
            for ti, tbl in enumerate(tables[:5]):
                rows = [[(c or "").replace("\n", " ") for c in r] for r in tbl if r]
                rows = [r for r in rows if sum(1 for c in r if c.strip()) >= 2]
                if len(rows) >= 3 and max(len(r) for r in rows) >= 3:
                    s = summarize(rows, name, f"page{pi+1}_t{ti+1}", n_rows_total=len(rows))
                    if s:
                        out.append(s)
            try:
                txt = page.extract_text() or ""
            except Exception:
                txt = ""
            if pi == 0 and out:
                out[-1]["pdf_text_head"] = txt[:800]
    finally:
        pdf.close()
    return out


def parse_member(b, name, depth=0):
    ext = os.path.splitext(name)[1].lower()
    try:
        if ext in (".xlsx", ".xlsm"):
            return parse_xlsx(b, name)
        if ext == ".xls":
            return parse_xls(b, name)
        if ext in (".csv", ".tsv", ".txt"):
            return parse_delim(b, name)
        if ext == ".docx":
            return parse_docx(b, name)
        if ext == ".pdf":
            return parse_pdf(b, name)
        if ext == ".zip" and depth < 2:
            out = []
            with zipfile.ZipFile(io.BytesIO(b)) as z:
                for i in z.infolist():
                    if i.is_dir() or i.file_size > 150_000_000:
                        continue
                    if os.path.splitext(i.filename)[1].lower() in TABLE_EXT | {".zip"}:
                        out += parse_member(z.read(i), name + "::" + i.filename, depth + 1)
            return out
    except Exception as ex:
        return [dict(file=name, sheet=None, n_rows=-1, n_cols=-1, header_row_index=-1, headers="[]", sample_rows="[]",
                     has_sample_id_col=False, has_accession_values=False, field_hits="{}", parse_error=str(ex)[:200])]
    return []


def inventory_zip(path):
    out = []
    with zipfile.ZipFile(path) as z:
        for i in z.infolist():
            if i.is_dir() or i.file_size > 150_000_000:
                continue
            if os.path.splitext(i.filename)[1].lower() in TABLE_EXT | {".zip"}:
                out += parse_member(z.read(i), i.filename)
    return out

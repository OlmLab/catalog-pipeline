"""Read full columns (sample-id + age) from a supplement table located by (zip path, member, sheet, header_row_index)."""
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
import io, os, re, zipfile, csv
from lxml import etree
import supp_parse

W = supp_parse.W


def _member_bytes(zip_path, member):
    parts = member.split("::")
    with zipfile.ZipFile(zip_path) as z:
        b = z.read(parts[0])
    for p in parts[1:]:
        with zipfile.ZipFile(io.BytesIO(b)) as z:
            b = z.read(p)
    return b


def read_rows(zip_path, member, sheet, max_rows=200000):
    b = _member_bytes(zip_path, member)
    ext = os.path.splitext(member)[1].lower()
    if ext in (".xlsx", ".xlsm"):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(b), read_only=True, data_only=True)
        ws = wb[sheet]
        rows = [list(r) for _, r in zip(range(max_rows), ws.iter_rows(values_only=True))]
        wb.close()
        return rows
    if ext == ".xls":
        import xlrd
        wb = xlrd.open_workbook(file_contents=b)
        ws = wb.sheet_by_name(sheet)
        return [ws.row_values(i) for i in range(min(ws.nrows, max_rows))]
    if ext in (".csv", ".tsv", ".txt"):
        txt = None
        for enc in ("utf-8-sig", "latin-1"):
            try:
                txt = b.decode(enc); break
            except Exception:
                pass
        lines = txt.splitlines()
        head = "\n".join(lines[:20])
        sep = "\t" if head.count("\t") >= head.count(",") and head.count("\t") > 0 else ("," if head.count(",") > 0 else ";")
        return list(csv.reader(lines[:max_rows], delimiter=sep))
    if ext == ".docx":
        with zipfile.ZipFile(io.BytesIO(b)) as z:
            root = etree.fromstring(z.read("word/document.xml"))
        ti = int(sheet.replace("table", "")) - 1
        tbl = list(root.iter(W + "tbl"))[ti]
        return [["".join(tc.itertext()).strip() for tc in tr.findall(W + "tc")] for tr in tbl.iter(W + "tr")]
    if ext == ".pdf":
        import pdfplumber
        m = re.match(r"page(\d+)_t(\d+)", sheet)
        pi, ti = int(m.group(1)) - 1, int(m.group(2)) - 1
        with pdfplumber.open(io.BytesIO(b)) as pdf:
            tbl = pdf.pages[pi].extract_tables()[ti]
        rows = [[(c or "").replace("\n", " ") for c in r] for r in tbl if r]
        return [r for r in rows if sum(1 for c in r if c.strip()) >= 2]
    return []


def get_columns(zip_path, member, sheet, header_row_index, wanted):
    rows = read_rows(zip_path, member, sheet)
    hdr = [supp_parse._clean(c) for c in rows[header_row_index]]
    idx = {}
    for w in wanted:
        for i, h in enumerate(hdr):
            if h == w:
                idx[w] = i; break
    out = {w: [] for w in wanted}
    for r in rows[header_row_index + 1:]:
        for w, i in idx.items():
            out[w].append(supp_parse._clean(r[i]) if i < len(r) else None)
    return out


UNIT_RX = [
    (re.compile(r"\bdays?\b|\bdol\b|day[_ ]?of[_ ]?life|postnatal[_ ]?day|\bd\b|infant_?age$|age_?d\b|\bpnd\b", re.I), "days"),
    (re.compile(r"\bweeks?\b|\bwks?\b|\bw\b|\bpma\b|gestational", re.I), "weeks"),
    (re.compile(r"\bmonths?\b|\bmos?\b|\bm\b|\bmonth", re.I), "months"),
    (re.compile(r"\byears?\b|\byrs?\b|\by\b", re.I), "years"),
]


def unit_from_header(h):
    for rx, u in UNIT_RX:
        if rx.search(h):
            return u
    return None


VAL_RX = re.compile(r"^\s*([-+]?\d+(?:\.\d+)?)\s*(d|day|days|w|wk|wks|week|weeks|m|mo|mos|month|months|y|yr|yrs|year|years)?\b", re.I)
CANON = {"d": "days", "day": "days", "days": "days", "w": "weeks", "wk": "weeks", "wks": "weeks", "week": "weeks", "weeks": "weeks",
         "m": "months", "mo": "months", "mos": "months", "month": "months", "months": "months", "y": "years", "yr": "years", "yrs": "years", "year": "years", "years": "years"}


def parse_age_value(v, default_unit, age_to_days):
    """Return age_days or None. Uses embedded unit if present, else header unit."""
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in ("birth", "meconium", "0"):
        return 0.0
    m = VAL_RX.match(s)
    if not m:
        m2 = re.match(r"^\s*(day|days|dol|week|weeks|wk|month|months|mo|year|years|d|w|m|y)\s*[_\-:]?\s*(\d+(?:\.\d+)?)\s*$", s)
        if not m2:
            return None
        u, num = m2.group(1), m2.group(2)
        u = "d" if u == "dol" else u
        unit = CANON.get(u)
        return age_to_days(num, unit) if unit else None
    num, u = m.group(1), m.group(2)
    unit = CANON.get(u.lower()) if u else default_unit
    if unit is None:
        return None
    return age_to_days(num, unit)

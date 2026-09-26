"""Deterministic parsers for R1 attribute -> target-field normalisation."""
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
import re
import pycountry
import infant_rule as IR

NULLS = {'', 'na', 'n/a', 'nan', 'none', 'null', 'missing', 'not collected', 'not provided', 'not applicable',
         'unknown', 'unspecified', 'not recorded', 'labcontrol test', 'missing: not provided', 'missing: not collected',
         'missing: not recorded', 'not available', 'missing: not applicable', '-', '?', 'nd', 'no data', 'not sure', 'not determined'}

def is_null(v):
    return v is None or str(v).strip().lower() in NULLS or str(v).strip().lower().startswith('missing')

NUM = r'[-+]?\d+(?:\.\d+)?'

# ---------------- age ----------------
UNIT_WORDS = {'d': 'days', 'day': 'days', 'days': 'days', 'w': 'weeks', 'wk': 'weeks', 'wks': 'weeks', 'week': 'weeks', 'weeks': 'weeks',
              'm': 'months', 'mo': 'months', 'mos': 'months', 'month': 'months', 'months': 'months', 'y': 'years', 'yr': 'years',
              'yrs': 'years', 'year': 'years', 'years': 'years', 'h': 'hours', 'hr': 'hours', 'hrs': 'hours', 'hour': 'hours', 'hours': 'hours'}
FACT = {'days': 1.0, 'weeks': 7.0, 'months': 30.4375, 'years': 365.25, 'hours': 1 / 24.0}

def to_days(v, unit):
    u = UNIT_WORDS.get(str(unit).strip().lower().rstrip('.'), None)
    if u is None:
        return None
    return float(v) * FACT[u]

def parse_age_numeric(v, unit_default):
    """Bare number in a known unit. Returns (days, note) or (None, reason)."""
    s = str(v).strip()
    if is_null(s):
        return None, 'null'
    m = re.fullmatch(NUM, s)
    if m:
        d = to_days(float(s), unit_default)
        return (round(d), 'numeric') if d is not None else (None, 'bad unit')
    # number with explicit unit overrides default
    return parse_age_text(s)

def parse_age_text(s):
    """Free text with units, ranges, ISO 8601, words. Returns (days, note)."""
    if is_null(s):
        return None, 'null'
    low = str(s).strip().lower()
    if re.fullmatch(r'(newborn|neonate|birth|at birth|day 0|d0|meconium)', low):
        return 0, 'word_newborn'
    m = re.fullmatch(r'(\d+)\s*\+\s*(\d)', low)  # 25+2 style is GA, not age
    if m:
        return None, 'ga_style'
    # range: '1-2 weeks', '04-06 mo', '6-12 months'
    m = re.fullmatch(r'(\d+(?:\.\d+)?)\s*(?:-|–|to)\s*(\d+(?:\.\d+)?)\s*([a-z]+)\.?', low)
    if m:
        a, b, u = m.groups()
        da, db = to_days(a, u), to_days(b, u)
        if da is None:
            return None, 'range bad unit'
        return round((da + db) / 2), f'range_midpoint {a}-{b} {u}'
    months, tag, note = IR.parse_age_months(str(s))
    if months is None:
        return None, 'unparsed'
    if tag == 'bare_assumed_years':
        return None, 'bare number without unit'
    if tag == 'range':
        return round(months * 30.4375), 'range_hi'
    return round(months * 30.4375), tag

# ---------------- gestational age ----------------
def parse_ga(v, unit_default):
    s = str(v).strip()
    if is_null(s):
        return None, 'null'
    low = s.lower()
    m = re.fullmatch(r'(\d+)\s*\+\s*(\d)', low) or re.fullmatch(r'(\d+)\s*w(?:eeks?|k)?\s*(\d)\s*d(?:ays?)?', low)
    if m:
        return round(int(m.group(1)) + int(m.group(2)) / 7.0, 2), 'weeks_plus_days'
    m = re.fullmatch(r'(\d+)\s*w(?:eeks?|k)?', low)
    if m:
        return float(m.group(1)), 'weeks'
    m = re.fullmatch(NUM, low)
    if m:
        x = float(low)
        if unit_default == 'days' or x > 100:
            return round(x / 7.0, 2), 'days_to_weeks'
        return round(x, 2), 'weeks'
    m = re.fullmatch(r'(\d+(?:\.\d+)?)\s*(weeks?|wks?)', low)
    if m:
        return float(m.group(1)), 'weeks'
    return None, 'unparsed'

def parse_bw(v):
    s = str(v).strip()
    if is_null(s):
        return None, 'null'
    low = s.lower().replace(',', '')
    m = re.fullmatch(r'(\d+(?:\.\d+)?)\s*(g|grams?|kg|kilograms?)?', low)
    if not m:
        return None, 'unparsed'
    x = float(m.group(1)); u = m.group(2) or ''
    if u.startswith('k') or (u == '' and x < 10):
        x *= 1000
    return round(x), 'grams'

# ---------------- categoricals ----------------
YES = {'yes', 'y', 'true', 't', '1', 'during', 'exposed', 'positive', 'pos', 'present', 'ja', 'oui', 'si', 'past use', 'current use', 'yes_current'}
NO = {'no', 'n', 'false', 'f', '0', 'never', 'not_during', 'unexposed', 'none', 'negative', 'neg', 'absent', 'nein', 'no antibiotics', 'no abx', 'nonec', 'no_nec'}

def parse_yesno(v, key=''):
    s = str(v).strip().lower()
    if is_null(s):
        return None, 'null'
    if s in YES:
        return 'yes', 'yesno'
    if s in NO:
        return 'no', 'yesno'
    if key == 'antibiotic_history':
        if s.startswith('i have not taken'):
            return 'no', 'agp_history'
        if s in ('week', 'month', '6 months', 'year'):
            return 'yes', 'agp_history_within_year'
        return None, 'unparsed'
    if key == 'days_on_abx':
        m = re.fullmatch(NUM, s)
        if m:
            return ('yes' if float(s) > 0 else 'no'), 'days_on_abx'
    if key in ('antibiotic', 'host_maternal_peripartum_abx', 'm_antibiotics'):
        # drug names -> yes
        if re.search(r'(cillin|mycin|cef|ceph|penem|floxacin|cycline|azole|vancomycin|gentamicin|clindamycin|sulfa|trimethoprim|nitrofurantoin|standacillin|metronidazole)', s):
            return 'yes', 'drug_name'
    if s in ('after', 'before'):
        return None, 'timing_ambiguous'
    return None, 'unparsed'

DELIV = [
    (r'^(cs|c[- _]?section|caesarean|cesarean|caesarian|cesarian|c|sc|cesarea|caesarea|sectio|caeserean|section|1_cs)$', 'c_section'),
    (r'(elective|planned|scheduled|pre[- ]?labou?r|without labou?r|no labou?r|cold)', 'c_section_elective'),
    (r'(emergen|unplanned|urgent|in labou?r|with labou?r|after labou?r|intrapartum|icsinoc)', 'c_section_emergency'),
    (r'(c[- _]?section|caesar|cesar|^cs\b|\bcs$|^cs[-_]|sectio)', 'c_section'),
    (r'^(vaginal|vaginal delivery|vaginally|vd|vb|svd|nvd|v|vag|natural|spontaneous vaginal delivery|spontaneous|normal|normal delivery|per vaginam|vaginal birth|vacuum|forceps|ventouse|assisted vaginal|vaginal_birth|0|vag_delivery)$', 'vaginal'),
    (r'(vagin|svd|spontaneous)', 'vaginal'),
]

def parse_delivery(v, key=''):
    s = str(v).strip().lower()
    if is_null(s):
        return None, 'null'
    if key == 'csection':  # AGP yes/no
        if s in YES: return 'c_section', 'yesno'
        if s in NO: return 'vaginal', 'yesno'
        return None, 'unparsed'
    if key in ('caesareansection', 'c_section_0_no_1_yes'):
        if s == '1': return 'c_section', 'coded'
        if s == '0': return 'vaginal', 'coded'
        return None, 'unparsed'
    if key == 'vaginal_delivery_0_no_1_yes':
        if s == '1': return 'vaginal', 'coded'
        if s == '0': return 'c_section', 'coded'
        return None, 'unparsed'
    if key == 'delivery_vvaginal_ccs_icsinoc':
        if s == 'v': return 'vaginal', 'coded'
        if s == 'c': return 'c_section', 'coded'
        return None, 'code_I_ambiguous'
    if key == 'delivery_mode_abx':
        if s.startswith('vd'): return 'vaginal', 'coded'
        if s.startswith('cs'): return 'c_section', 'coded'
        return None, 'unparsed'
    if key == 'delivery' and s in ('1', '2'):
        return None, 'coded_no_legend'
    for pat, val in DELIV:
        if re.search(pat, s):
            return val, 'regex'
    return None, 'unparsed'

FEED = [
    (r'^(exclusive(ly)?[ _-]?(breast|bf|breastfe[ed]+|breastmilk|breast milk)|ebf|breast ?milk|breastmilk|breastfed|breast|bf|b|human milk|exclusive|mother\'?s? ?milk|mbm|exclusisbreast|breastfeeding|exclusively breastfed|only breast milk)$', 'exclusive_breast'),
    (r'^(formula|ff|f|formula[ _-]?fed|exclusive(ly)? formula|formula milk|infant formula|control formula|standard formula|formula only|other milk)$', 'formula'),
    (r'^(mixed|mf|bf\+ff|breast\+formula|breast and formula|partial|partially breastfed|combination|combined|both|mixed feeding|breasfedformula|breastfed and formula|breast milk and formula|human mik and infant formula|human milk and infant formula|breastmilk\+formula)$', 'mixed'),
    (r'(solid|wean|complementary|table food|fs|bs)', 'weaned/solids'),
    (r'(mixed|partial|both|combin|and formula|\+)', 'mixed'),
    (r'(formula)', 'formula'),
    (r'(breast|human milk|mbm)', 'exclusive_breast'),
]

def parse_feeding(v, key=''):
    s = str(v).strip().lower()
    if is_null(s):
        return None, 'null'
    if key == 'diet_b_exclusisbreast_f_formula_bf_breasfedformula_bs_breasts':
        return {'b': 'exclusive_breast', 'f': 'formula', 'bf': 'mixed', 'bs': 'weaned/solids', 'fs': 'weaned/solids'}.get(s), 'coded'
    if key == 'diet_description':
        return {'exclusisbreast': 'exclusive_breast', 'formula': 'formula', 'breasfedformula': 'mixed', 'breastsolids': 'weaned/solids', 'formulasolids': 'weaned/solids'}.get(s), 'coded'
    if key == 'formula':
        if 'breast' in s: return 'exclusive_breast', 'coded'
        if 'formula' in s or 'hmo' in s: return 'formula', 'coded'
        return None, 'unparsed'
    if key == 'breastfeeding_status':
        return {'exclusive': 'exclusive_breast', 'partial': 'mixed', 'mixed': 'mixed', 'none': 'formula', 'no': 'formula', 'weaned': 'weaned/solids'}.get(s), 'coded'
    for pat, val in FEED:
        if re.search(pat, s):
            return val, 'regex'
    return None, 'unparsed'

def parse_percent_feeding(v, key):
    s = str(v).strip()
    if is_null(s) or not re.fullmatch(NUM, s):
        return None, 'null'
    x = float(s)
    if key == 'formula_percent':
        x = 100 - x
    if x >= 99.5: return 'exclusive_breast', 'percent'
    if x <= 0.5: return 'formula', 'percent'
    return 'mixed', 'percent'

def parse_sex(v, key=''):
    s = str(v).strip().lower()
    if is_null(s):
        return None, 'null'
    if key == 'legal_sex_0_m_1_f':
        return {'0': 'male', '1': 'female'}.get(s), 'coded'
    if key == 'phenotype':
        m = re.match(r'(female|male)_subject', s)
        return (m.group(1), 'phenotype') if m else (None, 'unparsed')
    if s in ('f', 'female', 'girl', 'fem', 'woman', 'w'): return 'female', 'sex'
    if s in ('m', 'male', 'boy', 'man'): return 'male', 'sex'
    return None, 'unparsed'

def parse_nec(v, key=''):
    s = str(v).strip().lower()
    if is_null(s):
        return None, 'null'
    if key == 'nec_medical_or_surgical':
        if s == 'nonec': return 'no', 'coded'
        if s in ('medical', 'surgical'): return 'yes', 'coded'
        return None, 'unparsed'
    if s in YES or s in ('y', 'nec', 'medical', 'surgical'): return 'yes', 'yesno'
    if s in NO or s == 'n': return 'no', 'yesno'
    return None, 'unparsed'

def parse_hmo(v, key=''):
    s = str(v).strip().lower()
    if is_null(s):
        return None, 'null'
    if 'hmo' in s: return 'yes', 'coded'
    if 'control formula' in s or 'breast' in s: return 'no', 'coded'
    return None, 'unparsed'

def parse_probiotic_freq(v, key=''):
    s = str(v).strip().lower()
    if is_null(s):
        return None, 'null'
    if s == 'never': return 'no', 'freq'
    if re.search(r'daily|regularly|occasionally|rarely', s): return 'yes', 'freq'
    return None, 'unparsed'

def parse_preterm_coded(v, key=''):
    s = str(v).strip().lower()
    if is_null(s):
        return None, 'null'
    return {'0': 'term', '1': 'preterm', '2': 'term'}.get(s), 'coded'

# ---------------- country ----------------
COUNTRY_FIX = {'usa': 'US', 'united states': 'US', 'united states of america': 'US', 'us': 'US', 'u.s.a.': 'US', 'uk': 'GB', 'united kingdom': 'GB', 'england': 'GB',
               'scotland': 'GB', 'wales': 'GB', 'great britain': 'GB', 'south korea': 'KR', 'korea': 'KR', 'republic of korea': 'KR', 'korea, republic of': 'KR',
               'russia': 'RU', 'iran': 'IR', 'vietnam': 'VN', 'viet nam': 'VN', 'tanzania': 'TZ', 'the netherlands': 'NL', 'netherlands': 'NL', 'holland': 'NL',
               'czech republic': 'CZ', 'czechia': 'CZ', 'taiwan': 'TW', 'hong kong': 'HK', 'macau': 'MO', 'bolivia': 'BO', 'venezuela': 'VE', 'laos': 'LA',
               'syria': 'SY', 'ivory coast': 'CI', "cote d'ivoire": 'CI', 'democratic republic of the congo': 'CD', 'drc': 'CD', 'congo': 'CG', 'gambia': 'GM',
               'the gambia': 'GM', 'moldova': 'MD', 'brunei': 'BN', 'cape verde': 'CV', 'swaziland': 'SZ', 'burma': 'MM', 'myanmar': 'MM', 'palestine': 'PS',
               'north korea': 'KP', 'tibet': 'CN', 'prc': 'CN', 'china:hong kong': 'HK', 'türkiye': 'TR', 'turkiye': 'TR', 'turkey': 'TR', 'mainland china': 'CN',
               'ussr': 'RU', 'uae': 'AE', 'north macedonia': 'MK', 'macedonia': 'MK', 'kosovo': 'XK', 'eswatini': 'SZ', 'micronesia': 'FM', 'timor-leste': 'TL',
               'east timor': 'TL', 'puerto rico': 'PR', 'greenland': 'GL', 'guam': 'GU', 'usa: puerto rico': 'PR'}
_cache = {}

def parse_country(v):
    s = str(v).strip()
    if is_null(s) or s.lower() in ('not applicable', 'restricted access', 'uncalculated'):
        return None, 'null'
    head = re.split(r'[:;,(]', s)[0].strip()
    low = head.lower()
    if low in _cache:
        return _cache[low]
    out = (None, 'unparsed')
    if low in COUNTRY_FIX:
        out = (COUNTRY_FIX[low], 'fix')
    else:
        try:
            c = pycountry.countries.lookup(head)
            out = (c.alpha_2, 'pycountry')
        except LookupError:
            try:
                c = pycountry.countries.search_fuzzy(head)
                if c:
                    out = (c[0].alpha_2, 'pycountry_fuzzy')
            except LookupError:
                pass
    _cache[low] = out
    return out

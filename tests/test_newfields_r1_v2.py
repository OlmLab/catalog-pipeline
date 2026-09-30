"""Route R1 for the 1.13.0 pack fields (catalog.scopes.newfields_r1_v2): diet / smoking_status / medication / stool_consistency_bristol
parsers, the model-output substring guards, and the build_gut_scope handling of `vocab_list` and ranged `int` fields."""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from catalog.scopes import build_gut_scope as bgs  # noqa: E402
from catalog.scopes import newfields_r1_v2 as nf  # noqa: E402

CFG = os.path.join(os.path.dirname(__file__), "..", "config")
DIET = nf.load_vocab(CFG, "diet")
MED = nf.load_vocab(CFG, "medication")
SMOKE = nf.load_vocab(CFG, "smoking")


def test_vocabularies_parse():
    assert {"omnivore", "vegan", "therapeutic_or_study_diet", "other_diet", "unknown"} <= set(DIET)
    assert {"never", "former", "current", "unknown"} == set(SMOKE)
    assert {"ppi", "none_reported", "other_medication", "unknown"} <= set(MED)


# ------------------------------------------------------------------------------------------------------------------ diet
DIET_OK = [
    ("host_diet", "Omnivore", "omnivore", 0.9), ("host_diet", "omnivore [ecocore_00000082]", "omnivore", 0.9), ("diet", "omnivour", "omnivore", 0.9),
    ("host_diet", "Non_veg", "omnivore", 0.9), ("diet", "Nonvegetarian", "omnivore", 0.9), ("diet", "Non-vegetarian", "omnivore", 0.9), ("host_diet", "Meat consumer", "omnivore", 0.9),
    ("dietary_regime_biospecimen", "Omnivorous diet", "omnivore", 0.9), ("diet_type", "Omnivore but do not eat red meat", "omnivore", 0.9),
    ("host_diet", "Normal diet", "omnivore", 0.7), ("host_diet", "no special diet", "omnivore", 0.7), ("s_specificdiet_v2", "No.", "omnivore", 0.7),
    ("special_diet_yn", "0", "omnivore", 0.7), ("dietary_restrictions_m3_biospecimen", "False", "omnivore", 0.7), ("specialized_diet_i_do_not_eat_a_specialized_diet", "true", "omnivore", 0.7),
    ("host_diet", "Vegan", "vegan", 0.9), ("s_specificdiet_v2_v2", "Vegan diet", "vegan", 0.9), ("host_diet", "Vegetarian", "vegetarian", 0.9), ("vegetarian", "1", "vegetarian", 0.85),
    ("host_diet", "Indian vegeterarian diet", "vegetarian", 0.9), ("host_diet", "Pescatarian", "pescatarian", 0.9), ("dietary_regime_biospecimen", "Pescetarian diet", "pescatarian", 0.9),
    ("host_diet", "Gluten free", "gluten_free", 0.9), ("host_diet", "ketogenic", "low_carbohydrate_or_ketogenic", 0.9), ("diet", "mediterranean diet", "mediterranean", 0.9),
    ("diet", "Med", "mediterranean", 0.7), ("host_diet", "MIND", "therapeutic_or_study_diet", 0.7), ("diet", "SCD", "therapeutic_or_study_diet", 0.9), ("host_diet", "EEN", "therapeutic_or_study_diet", 0.9),
    ("host_diet", "VLCD", "therapeutic_or_study_diet", 0.9), ("special_diet", "High protein diet 6 Weeks", "therapeutic_or_study_diet", 0.9), ("host_diet", "Low-gluten diet", "therapeutic_or_study_diet", 0.9),
    ("diet", "Fiber free Diet", "therapeutic_or_study_diet", 0.9), ("host_diet", "fasting+DASH", "therapeutic_or_study_diet", 0.9),
    ("host_diet", "Plant complementary feeding arm; infant feeding method: formula-fed", "therapeutic_or_study_diet", 0.9),
    ("diet", "Fiber Rich", "high_fibre_or_whole_food", 0.9), ("host_diet", "Western-type Diet (WD)", "western_or_processed", 0.9), ("host_diet", "Standard American", "western_or_processed", 0.9),
    ("diet", "Flexitarian", "other_diet", 0.9), ("host_diet", "lactose_free", "other_diet", 0.9), ("host_diet", "Paleo", "other_diet", 0.9), ("s_specificdiet_v2", "kosher", "other_diet", 0.9),
    ("specialized_diet_fodmap", "true", "therapeutic_or_study_diet", 0.85), ("specialized_diet_kosher", "yes", "other_diet", 0.85),
]
DIET_REJECT = [
    ("host_diet", "control", "arm_or_code"), ("host_diet", "habitual", "arm_or_code"), ("diet", "a", "arm_or_code"), ("diet", "B", "arm_or_code"), ("diet_type", "0", "arm_or_code"),
    ("diet_type", "1", "arm_or_code"), ("host_diet", "diet", "arm_or_code"), ("diet", "Control Diet", "arm_or_code"), ("host_diet", "Midpoint", "arm_or_code"), ("host_diet", "Farmer", "arm_or_code"),
    ("host_diet", "Veg", "arm_or_code"), ("special_diet", "other(to be specified)", "placeholder"), ("special_diet", "NA 0 weeks", "placeholder"), ("host_diet", "missing", "placeholder"),
    ("host_diet", "not collected", "placeholder"), ("host_diet", "", "placeholder"), ("host_diet", None, "placeholder"), ("vegetarian", "0", "flag_false"),
    ("specialized_diet_paleodiet_or_primal_diet", "no", "flag_false"), ("special_diet_yn", "1", "special_diet_unspecified"), ("restrictdiet_yn", "1", "special_diet_unspecified"),
    ("host_diet", "Purina Advanced Protocol Select Rodent 50 IF/6F Auto Diet (5V0F)", "non_human_diet"), ("diet", "hplc", "arm_or_code"), ("host_diet", "wmd", "arm_or_code"),
    ("diet", "uf_of", "arm_or_code"),
]
DIET_DEFER = ["Vegetarian but eat seafood", "Indian semi-vegetarian diet", "Mostly Paleo but eats sweeteners like honey", "Fermented foods high",
              "cheerios with milk, peanut butter or nutella sandwich for lunch, rice for dinner", "Locavore-ish"]


@pytest.mark.parametrize("key,raw,code,conf", DIET_OK)
def test_diet_code_accepts(key, raw, code, conf):
    r = nf.diet_code_for(key, raw, DIET)
    assert r.get("code") == code, r
    assert r["confidence"] == conf, r
    assert r["detail"]


@pytest.mark.parametrize("key,raw,reason", DIET_REJECT)
def test_diet_code_rejects(key, raw, reason):
    r = nf.diet_code_for(key, raw, DIET)
    assert r.get("reject") == reason, r


@pytest.mark.parametrize("raw", DIET_DEFER)
def test_diet_long_tail_deferred_to_model(raw):
    assert nf.diet_code_for("host_diet", raw, DIET).get("defer") is True


def test_diet_guard_requires_term_in_raw_and_match_term():
    assert nf.guard_diet({"code": "vegan", "term": "vegan diet"}, "vegan diet since 2018", DIET, "general_diet")[0] == "vegan"
    assert nf.guard_diet({"code": "vegan", "term": "vegan"}, "eats everything", DIET, "host_diet")[0] is None            # term not in raw
    assert nf.guard_diet({"code": "mediterranean", "term": "MIND"}, "MIND", DIET, "host_diet")[0] is None                # abbreviation of another code
    assert nf.guard_diet({"code": "vegetarian", "term": "Indian semi-vegetarian diet"}, "Indian semi-vegetarian diet", DIET, "host_diet")[0] is None  # hedged
    assert nf.guard_diet({"code": "western_or_processed", "term": "processed foods"}, "we avoid processed foods", DIET, "other_diet")[0] is None    # negated
    assert nf.guard_diet({"code": "other_diet", "term": "control diet"}, "HabD: control diet", DIET, "special_diet_details")[0] is None           # study arm
    assert nf.guard_diet({"code": "other_diet", "term": "Fermented"}, "Fermented", DIET, "host_diet")[0] == "other_diet"
    assert nf.guard_diet({"code": "other_diet", "term": "avoid constipating food"}, "We have him avoid constipating food", DIET, "s_specificdiet_v2")[0] is None  # narrative, not a named diet
    assert nf.guard_diet({"code": "western_or_processed", "term": "fast food a few times a week"}, "x fast food a few times a week", DIET, "general_diet")[0] is None
    assert nf.guard_diet({"code": "nonsense", "term": "x"}, "x", DIET, "host_diet")[0] is None
    assert nf.guard_diet({"code": None, "is_placeholder": True}, "NA", DIET, "host_diet")[1] == "utility_null"


# ------------------------------------------------------------------------------------------------------------------ smoking
SMOKE_OK = [
    ("smoking_status", "never", False, "never", 0.9), ("smoking", "Never smoked", False, "never", 0.9), ("smoker", "Nonsmoker", False, "never", 0.9), ("smoking", "non-smoker", False, "never", 0.9),
    ("smoking_frequency", "Never", False, "never", 0.9), ("smoking_history", "Never", False, "never", 0.9), ("smoker", "no", False, "never", 0.8), ("do_you_smoke", "N", False, "never", 0.8),
    ("smoke", "False", False, "never", 0.8), ("nicotine_consumption", "No", False, "never", 0.8), ("smoking", "0", True, "never", 0.7), ("tobacco_use", "0", True, "never", 0.7),
    ("smoking_status", "former", False, "former", 0.9), ("smoking", "Ex smoker", False, "former", 0.9), ("smoker", "ex-smoker", False, "former", 0.9), ("smoking", "quit 2010", False, "former", 0.9),
    ("smoking", "0-1 cigs (former)", False, "former", 0.9), ("smoking", "1 pack of cigarettes; stopped", False, "former", 0.9), ("smoking", "Stopped 12/1997", False, "former", 0.9),
    ("smoking", "10 cigs (1983-1993)", False, "former", 0.8), ("smoking", "1/2 pack 1998-2004", False, "former", 0.8), ("smoking", "10 cigs (unk-11/2011)", False, "former", 0.8),
    ("smoking", "Smoker", False, "current", 0.9), ("smoking", "Current", False, "current", 0.9), ("smoking", "Smoker occasionally", False, "current", 0.9), ("smoker", "ciggaretes", False, "current", 0.9),
    ("smoking_frequency", "everyday", False, "current", 0.9), ("smoking_frequency", "3-5 times a week", False, "current", 0.9), ("nicotine_consumption", "1-10 cigarettes/day", False, "current", 0.9),
    ("nicotine_consumption", ">20 cigarettes/day", False, "current", 0.9), ("smoking", "2 cigarettes QD (2009-pres)", False, "current", 0.9), ("smoker", "yes", False, "current", 0.8),
    ("do_you_smoke", "Y", False, "current", 0.8), ("smoke", "True", False, "current", 0.8), ("smoking", "1", True, "current", 0.7), ("tobacco_use", "1", True, "current", 0.7),
]
SMOKE_REJECT = [
    ("smoking_history", "0", False, "coded_scale"), ("smoking_history", "1", False, "coded_scale"), ("smoking_history", "2", False, "coded_scale"), ("smokingstatus", "2", False, "coded_scale"),
    ("smoker", "0", False, "coded_scale"), ("smoking", "1", False, "coded_scale"), ("smoking", "20+ years", False, "duration_only"), ("smoking", "less than 10 years", False, "duration_only"),
    ("smoking", "between 10-20 years", False, "duration_only"), ("smoking", "1/2 pack for 20 years", False, "duration_only"), ("smoking", "Smoked", False, "ambiguous_tense"),
    ("smoker", "Passive smoking", False, "passive_exposure"), ("smoking", "second-hand smoke at home", False, "passive_exposure"), ("smoking_history", "Yes", False, "history_yes_ambiguous"),
    ("smoking", "missing", False, "placeholder"), ("smoker", "not provided", False, "placeholder"), ("smoking_frequency", "Not applicable", False, "placeholder"), ("smoking", "NA", False, "placeholder"),
    ("smoking", "", False, "placeholder"), ("smoking", None, False, "placeholder"), ("smoking", "mariijuana", False, "unrecognised"), ("smoking", "N; marijuana", False, "unrecognised"),
    ("smoking", "unk(1971-2/2/1987)", False, "unrecognised"), ("smoking", "5-6 (1996-2006)", False, "unrecognised"), ("smoking", "12", False, "numeric_only"), ("smoking", "3 (1-2011-6-2011)", False, "unrecognised"),
]


@pytest.mark.parametrize("key,raw,binary,code,conf", SMOKE_OK)
def test_parse_smoking_accepts(key, raw, binary, code, conf):
    r = nf.parse_smoking(raw, key, binary_ok=binary)
    assert r.get("code") == code, r
    assert r["confidence"] == conf, r
    assert code in SMOKE


@pytest.mark.parametrize("key,raw,binary,reason", SMOKE_REJECT)
def test_parse_smoking_rejects(key, raw, binary, reason):
    r = nf.parse_smoking(raw, key, binary_ok=binary)
    assert r.get("reject") == reason, r


# ------------------------------------------------------------------------------------------------------------------ medication
MED_OK = [
    ("omeprazole", {"ppi"}), ("Omeprazol", {"ppi"}), ("protein-pump inhibitor, cannabis", {"ppi"}), ("Pantoprazole", {"ppi"}), ("prilosec", {"ppi"}), ("PPI", {"ppi"}),
    ("metformin", {"metformin"}), ("metformin, insulin, pnv, iron", {"metformin", "antidiabetic_other"}), ("glyburide, nifedipine", {"antidiabetic_other", "antihypertensive"}),
    ("rosuvastatin 10 mg qd, aspirin 80 mg qd", {"statin", "nsaid_or_aspirin"}), ("statins", {"statin"}), ("Lisinopril 40 mg daily, Hydrochlorothiazide 25 mg", {"antihypertensive"}),
    ("labetalol, pepcid, pnv", {"antihypertensive"}), ("ibuprofen", {"nsaid_or_aspirin"}), ("ibuprufen", {"nsaid_or_aspirin"}), ("trombyl, folacin", {"nsaid_or_aspirin"}),
    ("movicol, lergigan", {"laxative"}), ("Lactulose", {"laxative"}), ("Tylenol, MirLAX, bisacodyl", {"laxative"}), ("prednisone", {"corticosteroid"}), ("Prednisona", {"corticosteroid"}),
    ("Budesonide,Prednisone", {"corticosteroid"}), ("Pred 40 mg PO QD (6/2016-pres)", {"corticosteroid"}), ("Entocort 9 mg PO (2010-pres)", {"corticosteroid"}), ("steroids, azathioprine", {"corticosteroid", "immunosuppressant_or_biologic"}),
    ("mycophenolate mofetil", {"immunosuppressant_or_biologic"}), ("methotrexate", {"immunosuppressant_or_biologic"}), ("MTX", {"immunosuppressant_or_biologic"}), ("VDZ", {"immunosuppressant_or_biologic"}),
    ("IFX", {"immunosuppressant_or_biologic"}), ("ADA 40 mg SQ (10/2016-pres)", {"immunosuppressant_or_biologic"}), ("anti-PD1", {"immunosuppressant_or_biologic"}), ("anti-PD-L1", {"immunosuppressant_or_biologic"}),
    ("Pembrolizumab", {"immunosuppressant_or_biologic"}), ("CTLA4/PD1", {"immunosuppressant_or_biologic"}), ("Gilenya", {"immunosuppressant_or_biologic"}), ("Tecfidera", {"immunosuppressant_or_biologic"}),
    ("immunosuppressants", {"immunosuppressant_or_biologic"}), ("Chemotherapy", {"chemotherapy"}), ("Asparaginase", {"chemotherapy"}), ("ART", {"antiretroviral"}), ("FTC/TDF", {"antiretroviral"}),
    ("sertraline, iron, prazosin", {"antidepressant_or_antipsychotic", "antihypertensive"}), ("celexa, pnv", {"antidepressant_or_antipsychotic"}), ("probiotic", {"probiotic_or_prebiotic"}),
    ("inulin", {"probiotic_or_prebiotic"}), ("tylenol, motrin, norethindrone", {"nsaid_or_aspirin", "hormonal_contraceptive_or_hrt"}), ("omeprazole and metformin", {"ppi", "metformin"}),
    ("none", {"none_reported"}), ("No medication", {"none_reported"}), ("not taking any medication", {"none_reported"}), ("no meds", {"none_reported"}),
]
MED_REJECT = [
    ("control", "arm_or_code"), ("placebo", "arm_or_code"), ("FMT", "arm_or_code"), ("donor", "arm_or_code"), ("1", "arm_or_code"), ("3", "arm_or_code"), ("cannabis", "arm_or_code"),
    ("person14.ethanol", "arm_or_code"), ("68180-0353", "arm_or_code"), ("fiber mix", "arm_or_code"), ("no_glycan", "arm_or_code"), ("vancomycin_125mg_po_qid", "antibiotic_only"),
    ("antibiotic", "antibiotic_only"), ("antibiotic for tonsilitis", "antibiotic_only"), ("Antibiotics for pneumonia", "antibiotic_only"), ("clindamycin", "antibiotic_only"),
    ("ada unk (3/2015-7/2015)", "historical_window"), ("pred unk dose po (1999-2006; d/c intoler", "historical_window"), ("prior azathioprine, none current", "historical_window"),
    ("IFX unk dose IV (unk; failed therapy)", "historical_window"), ("budesonide 9 mg (11/2014-2/2015)", "historical_window"), ("ustekinumab 90 mg sq 12/2016", "dated_window_unclear"),
    ("ifx 2003", "dated_window_unclear"), ("missing", "placeholder"), ("not collected", "placeholder"), ("NA", "placeholder"), ("", "placeholder"), (None, "placeholder"),
]
MED_DEFER = ["levaxin", "prenatal vitamins", "anti-histaminic", "Dopamine agonist", "Famotidine", "asacol, pentasa"]


@pytest.mark.parametrize("raw,codes", MED_OK)
def test_med_codes_for_text_accepts(raw, codes):
    r = nf.med_codes_for_text(raw, MED)
    assert "codes" in r, r
    assert {c for c, _ in r["codes"]} == codes, r
    assert all(c in MED for c in codes)


@pytest.mark.parametrize("raw,reason", MED_REJECT)
def test_med_codes_for_text_rejects(raw, reason):
    r = nf.med_codes_for_text(raw, MED)
    assert r.get("reject") == reason, r


@pytest.mark.parametrize("raw", MED_DEFER)
def test_med_long_tail_deferred_to_model(raw):
    assert nf.med_codes_for_text(raw, MED).get("defer") is True


def test_med_partial_list_also_deferred():
    r = nf.med_codes_for_text("sertraline, iron, flonase, pnv, zyrtec, vit b12", MED)
    assert {c for c, _ in r["codes"]} == {"antidepressant_or_antipsychotic", "corticosteroid"} and r["defer_extra"] is True


def test_med_flag_values():
    assert nf.yes_no("yes") is True and nf.yes_no("Y") is True and nf.yes_no("1") is True and nf.yes_no("used") is True and nf.yes_no("1to3days") is True
    assert nf.yes_no("no") is False and nf.yes_no("n") is False and nf.yes_no("0") is False and nf.yes_no("not_used") is False and nf.yes_no("notreatment") is False
    assert nf.yes_no("prednisone") is None and nf.yes_no("9") is None and nf.yes_no(None) is None
    assert nf.MED_FLAG_KEYS["ppi_last_month"] == "ppi" and nf.MED_FLAG_KEYS["laxatives"] == "laxative" and nf.MED_FLAG_KEYS["antiretroviral_treatment"] == "antiretroviral"
    assert "ppi_day_365" not in nf.MED_FLAG_KEYS and "prior_ppi" not in nf.MED_FLAG_KEYS and "med_steroid_inhalation_albuterol" not in nf.MED_FLAG_KEYS
    assert "antibiotic_treatment_during_hospitalization" not in nf.MED_FLAG_KEYS  # antibiotics are antibiotic_exposure


def test_med_guard():
    acc, notes, none = nf.guard_med({"codes": [{"code": "other_medication", "term": "levaxin"}, {"code": "ppi", "term": "omeprazole"}]}, "levaxin, flukonazol", MED)
    assert acc == [("other_medication", "levaxin")] and any("omeprazole" in n for n in notes)
    acc, _, _ = nf.guard_med({"codes": [{"code": "other_medication", "term": "clindamycin"}]}, "clindamycin", MED)
    assert acc == []                                                                                     # antibiotic skipped
    acc, _, _ = nf.guard_med({"codes": [{"code": "bogus", "term": "levaxin"}]}, "levaxin", MED)
    assert acc == []
    acc, _, none = nf.guard_med({"codes": [], "none_stated": True}, "none", MED)
    assert none is True and acc == [("none_reported", "none")]
    acc, _, none = nf.guard_med({"codes": [], "none_stated": True}, "untreated", MED)
    assert none is False and acc == []                                                                    # 'untreated' is not a no-medication statement


# ------------------------------------------------------------------------------------------------------------------ bristol
BRISTOL_OK = [
    ("1", 1, 0.9), ("2", 2, 0.9), ("3", 3, 0.9), ("4", 4, 0.9), ("5", 5, 0.9), ("6", 6, 0.9), ("7", 7, 0.9), ("4.0", 4, 0.9), (" 3 ", 3, 0.9), ("type 4", 4, 0.9), ("Type 6", 6, 0.9),
    ("BSS 2", 2, 0.9), ("bristol 5", 5, 0.9), ("score: 3", 3, 0.9), ("bsfs=7", 7, 0.9), (4, 4, 0.9), (2.0, 2, 0.9), ("07", 7, 0.9), ("stool type 1", 1, 0.9),
    ("hard", 2, 0.7), ("Hard", 2, 0.7), ("constipated", 2, 0.7), ("normal", 4, 0.7), ("formed", 4, 0.7), ("loose", 6, 0.7), ("Loose stool", 6, 0.7), ("watery", 7, 0.7), ("liquid", 7, 0.7),
]
BRISTOL_REJECT = [
    ("type 3-4", "range"), ("type 5-7", "range"), ("type 1-2", "range"), ("3 to 4", "range"), ("4/5", "range"), ("3.5", "non_integer_mean"), ("5.333333333", "non_integer_mean"),
    ("4.25", "non_integer_mean"), ("grade-1", "unknown_scale"), ("grade-4", "unknown_scale"), ("Grade 2", "unknown_scale"), ("8", "out_of_range"), ("0.5", "non_integer_mean"),
    ("12", "out_of_range"), ("soft", "textual_unmapped"), ("mushy", "textual_unmapped"), ("hard and loose", "textual_ambiguous"), ("0", "placeholder"), ("missing", "placeholder"),
    ("not collected", "placeholder"), ("NA", "placeholder"), ("", "placeholder"), (None, "placeholder"), ("-", "placeholder"), ("??", "unrecognised"), ("n/a", "placeholder"),
]


@pytest.mark.parametrize("raw,value,conf", BRISTOL_OK)
def test_parse_bristol_accepts(raw, value, conf):
    r = nf.parse_bristol(raw)
    assert r.get("value") == value and r["confidence"] == conf, r
    assert 1 <= r["value"] <= 7


@pytest.mark.parametrize("raw,reason", BRISTOL_REJECT)
def test_parse_bristol_rejects(raw, reason):
    r = nf.parse_bristol(raw)
    assert r.get("reject") == reason, r


# ------------------------------------------------------------------------------------------------------------------ determination rows
def test_det_row_schema():
    r = nf.det_row("SAMEA1", "diet", "PRJEB1", "Vegan", "vegan", 0.9, "host_diet", "SAMEA1", "Vegan")
    assert list(r) == nf.DET_COLS
    assert r["route"] == "R1" and r["scope"] == "sample" and r["evidence_source"] == "biosample.attribute:host_diet" and r["determined_by"] == "gut_newfields_r1_v2"
    assert r["src_track"] == "gut_all_v1" and r["release_added"] == "R2026.13" and r["package_added"] == "1.13.0" and r["evidence_limited_to_abstract"] == 0.0
    long = nf.det_row("S", "diet_detail", "P", "x", "y", 0.9, "k", "S", " ".join(["word"] * 30))
    assert len(long["evidence_quote"].split()) <= 12


def test_term_in_and_negation():
    assert nf.term_in("omnivor", "Omnivore") and nf.term_in("statin", "statins") and nf.term_in("chemotherap", "chemotherapy")
    assert not nf.term_in("rat", "ulcerative") and not nf.term_in("formula", "Formulated Diet") and not nf.term_in("ART", "part of")
    assert nf.negated("processed", "we avoid processed foods") and nf.negated("gluten", "gluten free") and not nf.negated("vegan", "vegan diet")


# ------------------------------------------------------------------------------------------------------------------ build_gut_scope: vocab_list + int
def test_pack_fields_types():
    pf = bgs.pack_fields(bgs._load_pack(CFG))
    assert pf["vocab_list"] == {"medication": "config/vocab/medication.yaml"}
    assert pf["int_range"] == {"stool_consistency_bristol": (1, 7)}
    assert {"diet", "smoking_status", "lifestyle", "health_condition"} <= set(pf["vocab"])
    assert {"diet", "diet_detail", "smoking_status", "medication", "medication_detail", "stool_consistency_bristol"} <= set(pf["fields"])


def test_clean_vocab_list_and_int():
    codes = {"ppi", "statin", "none_reported"}
    assert bgs.clean_vocab_list("statin;ppi", codes) == "ppi;statin"
    assert bgs.clean_vocab_list("ppi;bogus;ppi", codes) == "ppi"
    assert bgs.clean_vocab_list("bogus", codes) is None and bgs.clean_vocab_list(None, codes) is None
    assert bgs.clean_int("4", 1, 7) == 4 and bgs.clean_int("4.0", 1, 7) == 4 and bgs.clean_int(7, 1, 7) == 7
    assert bgs.clean_int("4.5", 1, 7) is None and bgs.clean_int("8", 1, 7) is None and bgs.clean_int("0", 1, 7) is None and bgs.clean_int("x", 1, 7) is None


def test_validate_vocab_fields_drops_invalid_codes_and_rows():
    pf = bgs.pack_fields(bgs._load_pack(CFG))
    rows = [
        dict(field_name="medication", value_normalized="ppi;bogus", src_track="gut_all_v1"), dict(field_name="medication", value_normalized="bogus", src_track="gut_all_v1"),
        dict(field_name="medication", value_normalized="statin;ppi", src_track="gut_all_v1"), dict(field_name="stool_consistency_bristol", value_normalized="4", src_track="gut_all_v1"),
        dict(field_name="stool_consistency_bristol", value_normalized="9", src_track="gut_all_v1"), dict(field_name="stool_consistency_bristol", value_normalized="3.5", src_track="gut_all_v1"),
        dict(field_name="diet", value_normalized="vegan", src_track="gut_all_v1"), dict(field_name="diet", value_normalized="carnivore", src_track="gut_all_v1"),
        dict(field_name="smoking_status", value_normalized="former", src_track="gut_all_v1"), dict(field_name="smoking_status", value_normalized="sometimes", src_track="gut_all_v1"),
    ]
    det = pd.DataFrame(rows)
    out, dropped = bgs.validate_vocab_fields(det, pf, CFG)
    assert dropped["medication"] == 1 and dropped["medication__codes"] == 2 and dropped["stool_consistency_bristol"] == 2 and dropped["diet"] == 1 and dropped["smoking_status"] == 1
    assert sorted(out.loc[out.field_name == "medication", "value_normalized"]) == ["ppi", "ppi;statin"]
    assert list(out.loc[out.field_name == "stool_consistency_bristol", "value_normalized"]) == ["4"]
    assert list(out.loc[out.field_name == "diet", "value_normalized"]) == ["vegan"]

"""Haiku batched abstract screen. Set SLICE (parquet path) and OUT_PREFIX before exec.
Expects llm_batch_common imported and validators loaded; `host` in namespace."""
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
import json, pandas as pd
from llm_batch_common import run_batches, V

MODEL = resolve_model("screen")
BATCH = globals().get("BATCH", 25)
MAX_TOKENS = globals().get("MAX_TOKENS", 8000)
SLOTS = ["is_human", "has_infant_0_36m", "is_shotgun", "data_type"]

SYSTEM = """You screen biomedical paper records (title + abstract) for a catalog of HUMAN INFANT (0-36 months) GUT SHOTGUN-METAGENOME studies. Judge each paper ONLY from the text given. For each paper answer four slots:
- is_human: yes/no/unsure. Animal models (mouse, piglet, macaque, calf, rat pup) are 'no'. Human cohorts 'yes'.
- has_infant_0_36m: yes/no/unsure. 'yes' needs newborns, neonates, infants, toddlers, preterm babies, first 1000 days, age <=3 years, or mother-infant pairs with infant sampling. Children older than 3 y only -> 'no'. Pregnant women only, adults only -> 'no'. Salmonella Infantis / Bifidobacterium infantis are bacteria, NOT infants.
- is_shotgun: yes/no/unsure. 'yes' for whole-metagenome shotgun / WGS metagenomics / metagenome-assembled genomes / strain-level metagenomics. 16S/ITS amplicon-only, metatranscriptomics-only, isolate genome sequencing, culturomics, metabolomics -> 'no'. If the abstract does not name the method -> 'unsure'.
- data_type: primary_new_data / reanalysis_of_public_data / review_or_method / unsure.
For every slot give ONE evidence quote copied VERBATIM (<=12 words) from the title or abstract and its source label ('paper.title' or 'paper.abstract'); if no text supports the answer, set quote to the most relevant phrase and confidence <=0.5. Never invent text. HARD LIMIT: every quote is at most 12 words — choose the shortest decisive verbatim span (3-8 words is ideal); a quote longer than 12 words is rejected by the validator. Confidence 0-1 per slot. You MUST return an entry for EVERY paper id given, in order; never skip one."""

TOOL = {
    "name": "record_paper_screen",
    "description": "Record the four-slot screen for every paper in the batch, in the same order as given.",
    "input_schema": {
        "type": "object",
        "properties": {"papers": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "is_human": {"type": "string", "enum": ["yes", "no", "unsure"]},
                "has_infant_0_36m": {"type": "string", "enum": ["yes", "no", "unsure"]},
                "is_shotgun": {"type": "string", "enum": ["yes", "no", "unsure"]},
                "data_type": {"type": "string", "enum": ["primary_new_data", "reanalysis_of_public_data", "review_or_method", "unsure"]},
                "evidence": {"type": "object", "properties": {
                    s: {"type": "object", "properties": {"source": {"type": "string", "enum": ["paper.title", "paper.abstract"]},
                                                          "quote": {"type": "string"}}, "required": ["source", "quote"]} for s in SLOTS},
                    "required": SLOTS},
                "confidence": {"type": "object", "properties": {s: {"type": "number"} for s in SLOTS}, "required": SLOTS},
            },
            "required": ["id"] + SLOTS + ["evidence", "confidence"]}}},
        "required": ["papers"]}}


def fmt(p):
    return f"### PAPER id={p.id}\nTITLE: {p.title}\nYEAR: {p.pubYear} TYPES: {p.pubTypeList}\nABSTRACT: {p.abstractText or '(no abstract)'}\n"


df = pd.read_parquet(SLICE)
df["id"] = df["id"].astype(str)
requests, metas = [], []
for i in range(0, len(df), BATCH):
    b = df.iloc[i:i + BATCH]
    prompt = f"Screen the following {len(b)} papers. Return one entry per paper, same order, using the ids given.\n\n" + "\n".join(fmt(p) for p in b.itertuples())
    requests.append({"prompt": prompt, "system": SYSTEM, "model": MODEL, "tools": [TOOL],
                     "tool_choice": {"type": "tool", "name": TOOL["name"]}, "max_tokens": MAX_TOKENS})
    metas.append({"ids": list(b["id"]), "slots": SLOTS})


def make_rows(meta, parsed, res):
    out = []
    got = {str(p.get("id")): p for p in (parsed.get("papers") or []) if isinstance(p, dict)}
    for rid in meta["ids"]:
        p = got.get(rid)
        if not p:
            r = V["sentinel_row"](rid, "infant_screen_missing", MODEL, note="paper missing from batch output")
            out.append(r)
            continue
        for slot in SLOTS:
            ev = (p.get("evidence") or {}).get(slot) or {}
            out.append({"record_id": rid, "slot": slot, "value": p.get(slot), "outcome": "predicted",
                        "confidence": (p.get("confidence") or {}).get(slot),
                        "evidence": [{"source": ev.get("source", "paper.abstract"), "quote": str(ev.get("quote", ""))[:120]}],
                        "model": MODEL})
    return out


screen_df, stats = run_batches(requests, metas, make_rows, f"{OUT_PREFIX}.parquet", MODEL,
                               max_concurrency=8, checkpoint_every=200, log_path=f"{OUT_PREFIX}_stats.json")
print(json.dumps(stats))
print(screen_df.groupby("slot")["value"].value_counts().to_dict() if "slot" in screen_df else screen_df.shape)

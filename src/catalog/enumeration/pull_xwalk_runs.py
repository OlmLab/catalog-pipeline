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

import sys, os, io, time, json
# (sys.path handled by the repo layout shim above)
import pandas as pd, pyarrow as pa, pyarrow.parquet as pq
import harvest_lib as HL, scope_constants as SC
FIELDS = ["run_accession","study_accession","sample_accession","library_source","library_strategy","tax_id","host_tax_id","study_title","sample_title","sample_alias","library_name"]
SHOT = '(library_strategy="WGS" OR library_strategy="WXS")'
jobs = [("metagenomic_shot", f'library_source="METAGENOMIC" AND {SHOT}')]
mis = " OR ".join(f"tax_eq({t})" for t in sorted(SC.TAXA_MISFILED_FRAME))
jobs.append(("genomic_misfiled", f'library_source="GENOMIC" AND {SHOT} AND ({mis})'))
for tag, q in jobs:
    n = HL.ena_count("read_run", q, purpose=f"cohort_xwalk_count:{tag}")
    print(tag, "expected", n, flush=True); t0=time.time()
    tsv = HL.ena_search("read_run", q, FIELDS, limit=0, purpose=f"cohort_xwalk_pull:{tag}")
    print(tag, "fetched chars", len(tsv or ""), round(time.time()-t0), flush=True)
    writer=None; got=0
    for ch in pd.read_csv(io.StringIO(tsv), sep="\t", dtype=str, on_bad_lines="skip", low_memory=False, chunksize=200000, keep_default_na=False):
        for c in FIELDS:
            if c not in ch: ch[c]=""
        ch = ch[FIELDS]
        t = pa.Table.from_pandas(ch, preserve_index=False)
        if writer is None: writer = pq.ParquetWriter(f"xwalk_runs_{tag}.parquet", t.schema, compression="zstd")
        writer.write_table(t); got += len(ch)
    if writer: writer.close()
    print(tag, "rows", got, "expected", n, flush=True)

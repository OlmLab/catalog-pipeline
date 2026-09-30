"""Run->sample->study index for the join step: every METAGENOMIC WGS/WXS run (all taxa) plus the
misfiled-candidate slices (GENOMIC WGS/WXS on human/metagenome records; METAGENOMIC OTHER/Targeted-Capture).
Streaming limit=0, chunked parquet."""
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
import io, sys, time
from pathlib import Path
import pandas as pd, pyarrow as pa, pyarrow.parquet as pq
# (sys.path handled by the repo layout shim above)
import harvest_lib as HL

OUT = Path("run_index"); OUT.mkdir(exist_ok=True)
FIELDS = ["run_accession", "study_accession", "sample_accession", "secondary_sample_accession",
          "library_source", "library_strategy", "tax_id", "host_tax_id"]
HUM = '(host_tax_id=9606 OR tax_id=9606 OR scientific_name="*metagenome*" OR host="Homo sapiens")'
SLICES = {
    "meta_wgs": 'library_source="METAGENOMIC" AND (library_strategy="WGS" OR library_strategy="WXS")',
    "genomic_wgs_human": f'library_source="GENOMIC" AND (library_strategy="WGS" OR library_strategy="WXS") AND {HUM}',
    "meta_other": 'library_source="METAGENOMIC" AND (library_strategy="OTHER" OR library_strategy="Targeted-Capture")',
    "other_source_wgs_human": f'(library_source="OTHER" OR library_source="SYNTHETIC") AND (library_strategy="WGS" OR library_strategy="WXS") AND {HUM}',
}

def pull(name, query, chunk=200_000):
    out = OUT / f"{name}.parquet"
    if out.exists():
        return pq.read_metadata(out).num_rows
    n_expected = HL.ena_count("read_run", query, purpose="biosample_sweep_count")
    t0 = time.time()
    body = HL.ena_search("read_run", query, FIELDS, limit=0, purpose="biosample_sweep_runindex")
    n, writer = 0, None
    for df in pd.read_csv(io.StringIO(body), sep="\t", dtype=str, keep_default_na=False, chunksize=chunk, quoting=3):
        df = df[FIELDS]; df["slice"] = name
        tbl = pa.Table.from_pandas(df, preserve_index=False)
        if writer is None:
            writer = pq.ParquetWriter(out, tbl.schema, compression="zstd")
        writer.write_table(tbl); n += len(df)
    if writer: writer.close()
    print(f"{name}\texpected={n_expected}\tgot={n}\t{time.time()-t0:.0f}s\tbytes={len(body)}", flush=True)
    return n

if __name__ == "__main__":
    for k, q in SLICES.items():
        try: pull(k, q)
        except Exception as e: print(k, "ERROR", type(e).__name__, str(e)[:200], flush=True)

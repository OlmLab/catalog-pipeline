"""
BioSample-attribute sweep, ENA side. Pulls ENA `sample` records that can fire the infant rule:
  (H) human-annotated samples with an age or dev_stage value, and
  (T) samples (any host) whose sample_title / description / sample_description matches an
      infant text pattern (portal wildcard), filtered locally afterwards.
Every pull goes through harvest_lib (cached). limit=0 streaming, chunked parquet writes.
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
import io, sys, os, json, time
from pathlib import Path
import pandas as pd
import pyarrow as pa, pyarrow.parquet as pq
# (sys.path handled by the repo layout shim above)
import harvest_lib as HL

OUT = Path("ena_samples"); OUT.mkdir(exist_ok=True)
FIELDS = ["sample_accession", "secondary_sample_accession", "study_accession", "tax_id",
          "scientific_name", "host_tax_id", "host", "host_scientific_name", "host_sex", "sex",
          "age", "dev_stage", "host_body_site", "tissue_type", "isolation_source",
          "environmental_medium", "collection_date", "first_public", "sample_title",
          "description", "sample_description", "sample_alias", "center_name", "target_gene",
          "serovar", "sub_species", "strain"]
HUMAN = '(host_tax_id=9606 OR tax_id=9606 OR host="Homo sapiens")'
TEXT_TERMS = ["*infant*", "*neonat*", "*newborn*", "*preterm*", "*premature*", "*toddler*",
              "*meconium*", "*NICU*", "*days old*", "*day old*", "*day-old*", "*weeks old*",
              "*week old*", "*week-old*", "*months old*", "*month old*", "*month-old*",
              "*months-old*", "*weeks-old*", "*days-old*"]
YEARS = [("1900-01-01", "2015-12-31"), ("2016-01-01", "2018-12-31"), ("2019-01-01", "2020-12-31"),
         ("2021-01-01", "2022-12-31"), ("2023-01-01", "2023-12-31"), ("2024-01-01", "2024-12-31"),
         ("2025-01-01", "2030-12-31")]

def text_clause(field):
    return "(" + " OR ".join(f'{field}="{t}"' for t in TEXT_TERMS) + ")"

SLICES = {}
# H1: host 9606 with age (96k) -- one pull
SLICES["h_host9606_age"] = 'host_tax_id=9606 AND age="*"'
SLICES["h_host9606_dev"] = 'host_tax_id=9606 AND dev_stage="*"'
SLICES["h_hosttext_age"] = 'host="Homo sapiens" AND age="*"'
SLICES["h_tax9606_dev"] = 'tax_id=9606 AND dev_stage="*"'
# H2: tax 9606 with age (1.37M) -- by first_public window
for a, b in YEARS:
    SLICES[f"h_tax9606_age_{a[:4]}"] = f'tax_id=9606 AND age="*" AND first_public>={a} AND first_public<={b}'
# T: infant text anywhere (any host)
for fld in ["sample_title", "description", "sample_description"]:
    SLICES[f"t_{fld}"] = text_clause(fld)
SLICES["t_devstage_any"] = 'dev_stage="*" AND (scientific_name="*metagenome*" OR host_tax_id=9606 OR tax_id=9606)'

def pull(name, query, chunk=100_000):
    out = OUT / f"{name}.parquet"
    if out.exists():
        return pq.read_metadata(out).num_rows
    n_expected = HL.ena_count("sample", query, purpose="biosample_sweep_count")
    t0 = time.time()
    body = HL.ena_search("sample", query, FIELDS, limit=0, purpose="biosample_sweep_pull")
    if not isinstance(body, str):
        raise RuntimeError(f"{name}: non-text body {type(body)}")
    n = 0
    writer = None
    for df in pd.read_csv(io.StringIO(body), sep="\t", dtype=str, keep_default_na=False,
                          chunksize=chunk, quoting=3):
        for c in FIELDS:
            if c not in df.columns:
                df[c] = ""
        df = df[FIELDS]
        df["ena_slice"] = name
        tbl = pa.Table.from_pandas(df, preserve_index=False)
        if writer is None:
            writer = pq.ParquetWriter(out, tbl.schema, compression="zstd")
        writer.write_table(tbl)
        n += len(df)
    if writer is not None:
        writer.close()
    else:
        pd.DataFrame(columns=FIELDS + ["ena_slice"]).to_parquet(out)
    print(f"{name}\texpected={n_expected}\tgot={n}\t{time.time()-t0:.0f}s\tbytes={len(body)}", flush=True)
    return n

if __name__ == "__main__":
    tot = 0
    for name, q in SLICES.items():
        try:
            tot += pull(name, q)
        except Exception as e:
            print(f"{name}\tERROR\t{type(e).__name__}: {str(e)[:200]}", flush=True)
    print("TOTAL_ROWS", tot)

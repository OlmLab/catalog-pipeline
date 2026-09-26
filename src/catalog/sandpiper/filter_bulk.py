"""One-pass streaming filter of sandpiper2.0.0.gtdb.csv.gz (tab-separated: sample, filled_coverage, taxonomy)
to the catalog's matched runs. Writes sp/sandpiper_profiles_runs_raw.parquet and sp/filter_log.json.
Usage: python sp/filter_bulk.py [--partial]  (partial = tolerate truncated gzip, for a dry run)"""
import sys, gzip, json, time, os
import pandas as pd, pyarrow as pa, pyarrow.parquet as pq
PARTIAL = "--partial" in sys.argv
SRC = os.environ.get("SANDPIPER_BULK", f"sp/sandpiper{os.environ.get('SANDPIPER_VERSION', '2.0.0')}.gtdb.csv.gz")  # shim 2026-09-26 (R3-4)
OUT = "sp/sandpiper_profiles_runs_raw.parquet" if not PARTIAL else "sp/_partial_profiles.parquet"
matched = set(pd.read_parquet("sp/matched_runs.parquet")["run_accession"])
t0 = time.time(); n_rows = 0; n_kept = 0; runs_seen = set(); runs_kept = set(); n_chunks = 0
writer = None
schema = pa.schema([("run", pa.string()), ("coverage_filled", pa.float64()), ("taxonomy", pa.string())])
try:
    with gzip.open(SRC, "rt") as fh:
        for chunk in pd.read_csv(fh, sep="\t", chunksize=5_000_000, dtype={"sample": "string", "taxonomy": "string"}):
            n_chunks += 1; n_rows += len(chunk)
            runs_seen.update(chunk["sample"].unique().tolist())
            keep = chunk[chunk["sample"].isin(matched)]
            if len(keep):
                n_kept += len(keep); runs_kept.update(keep["sample"].unique().tolist())
                tbl = pa.Table.from_pandas(keep.rename(columns={"sample": "run", "filled_coverage": "coverage_filled"})[["run", "coverage_filled", "taxonomy"]], schema=schema, preserve_index=False)
                if writer is None:
                    writer = pq.ParquetWriter(OUT, schema, compression="zstd")
                writer.write_table(tbl)
            if n_chunks % 5 == 0:
                print(f"chunk {n_chunks}: rows {n_rows:,} kept {n_kept:,} runs_seen {len(runs_seen):,} runs_kept {len(runs_kept):,} {time.time()-t0:.0f}s", flush=True)
except (EOFError, OSError) as e:
    if not PARTIAL:
        raise
    print("partial read stopped:", repr(e), flush=True)
finally:
    if writer is not None:
        writer.close()
log = {"source": SRC, "partial": PARTIAL, "rows_scanned": n_rows, "rows_kept": n_kept, "runs_seen": len(runs_seen), "runs_kept": len(runs_kept),
       "matched_runs_expected": len(matched), "matched_runs_missing_from_bulk": sorted(matched - runs_kept)[:50], "n_missing": len(matched - runs_kept),
       "seconds": round(time.time() - t0, 1), "output": OUT, "output_bytes": os.path.getsize(OUT) if os.path.exists(OUT) else 0}
json.dump(log, open("sp/filter_log.json" if not PARTIAL else "sp/_partial_filter_log.json", "w"), indent=1)
print(json.dumps({k: v for k, v in log.items() if k != "matched_runs_missing_from_bulk"}), flush=True)

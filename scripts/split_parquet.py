"""Split a large parquet into row-group-aligned parts below a byte budget (GitHub keeps committed files < 100 MB).

usage: python scripts/split_parquet.py IN.parquet OUT_PREFIX [--max-mb 90]
writes OUT_PREFIX_part0.parquet, _part1.parquet, … plus OUT_PREFIX.sha256 (one line per part). Parts concatenate back with
pandas.concat([pd.read_parquet(p) for p in sorted(glob('OUT_PREFIX_part*.parquet'))]).
"""
import argparse, glob, hashlib, os
import pyarrow as pa, pyarrow.parquet as pq

ap = argparse.ArgumentParser(); ap.add_argument("src"); ap.add_argument("prefix"); ap.add_argument("--max-mb", type=float, default=90)
a = ap.parse_args()
pf = pq.ParquetFile(a.src)
n_parts = max(1, int(os.path.getsize(a.src) / (a.max_mb * 1e6)) + 1)
rows_per = -(-pf.metadata.num_rows // n_parts)
for old in glob.glob(a.prefix + "_part*.parquet"):
    os.remove(old)
writer, part, in_part, written = None, 0, 0, []
for batch in pf.iter_batches(batch_size=1_000_000):
    if writer is None:
        path = f"{a.prefix}_part{part}.parquet"; writer = pq.ParquetWriter(path, pf.schema_arrow, compression="zstd"); written.append(path)
    writer.write_table(pa.Table.from_batches([batch])); in_part += batch.num_rows
    if in_part >= rows_per:
        writer.close(); writer = None; part += 1; in_part = 0
if writer is not None:
    writer.close()
with open(a.prefix + ".sha256", "w") as f:
    for p in written:
        f.write(hashlib.sha256(open(p, "rb").read()).hexdigest() + "  " + os.path.basename(p) + "\n")
print(len(written), [round(os.path.getsize(p) / 1e6, 1) for p in written])

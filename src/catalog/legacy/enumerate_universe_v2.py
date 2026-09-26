"""
Step 2 (v2, 2026-09-18) -- re-enumeration of the human DNA-shotgun metagenome universe
with the two v1 enumeration bugs fixed and three new frames added.

Fixes / additions relative to enumerate_universe.py (v1):
  (a) "human feces metagenome" is taxid 2705415 in ENA (v1 used 3007725 -> 0 runs);
      generic taxon 256318 "metagenome" added as a SECONDARY frame (host adjudicated later).
  (b) the OTHER/Targeted-Capture adjudication slice is enumerated for tax_eq(9606)
      (v1 ran only the WGS/WXS slice for tax_eq(9606)).
  (c) frame-free slice host_tax_id=9606 x METAGENOMIC x {WGS,WXS,OTHER,Targeted-Capture}
      -- pulled as two queries (shot / adj) whose union is the frame-free slice; the
      single-query count is recorded in the audit as a consistency check.
  (d) host_scientific_name="Homo sapiens" slice (some submitters fill only the name), and
  (e) free-text host in {"Homo sapiens","human","Human"} slice.

Paging: ENA's `offset` parameter was observed broken on this endpoint (empty body at
offset=50000, see v1 docstring), so every slice is pulled with limit=0 and the body is
parsed in 100k-row chunks into a pyarrow ParquetWriter -- no slice is ever held as a single
DataFrame. Every pull is checked against the count endpoint; mismatches are recorded.

Usage: python enumerate_universe_v2.py [--counts-only]
Outputs: enum_v2/<tag>.parquet + <tag>.audit.json, enumeration_audit_v2.csv,
         universe_runs_v2_full.parquet (all slices, deduped by run_accession, found_by_v2).
"""
import io
import json
import sys
import time
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, ".")
import harvest_lib as HL
import scope_constants_v2 as SC

OUT = Path("enum_v2"); OUT.mkdir(exist_ok=True)
CHUNK = 100_000

# identical to v1 LEAN_FIELDS (43 columns) so v1 and v2 run tables are schema-compatible
LEAN_FIELDS = [
    "run_accession", "study_accession", "secondary_study_accession",
    "sample_accession", "secondary_sample_accession", "experiment_accession",
    "library_strategy", "library_source", "library_selection", "library_layout",
    "library_name", "target_gene", "instrument_platform", "instrument_model",
    "read_count", "base_count", "nominal_length",
    "tax_id", "scientific_name", "host_tax_id", "host_scientific_name",
    "host_body_site", "host_status", "host_phenotype", "age", "dev_stage",
    "disease", "country", "first_public", "center_name", "project_name",
    "study_title", "sample_title", "serovar", "sub_species", "strain",
    "isolate", "checklist", "environmental_medium", "isolation_source",
    "experimental_factor", "extraction_protocol", "environmental_sample",
]
assert len(LEAN_FIELDS) == 43
assert set(LEAN_FIELDS) <= set(SC.ENA_RUN_FIELDS)

SHOT = SC.ena_shotgun_clause()
ADJ = SC.ena_adjudicate_clause()
ALL4 = SC.ena_all_strategies_clause()


def build_jobs():
    jobs = []
    for tax in sorted(SC.TAXA_ALL_FRAME_V2):
        jobs.append((f"tax{tax}_shot", f"tax_eq({tax}) AND {SHOT}"))
        jobs.append((f"tax{tax}_adj", f"tax_eq({tax}) AND {ADJ}"))
    for name, clause in SC.HOST_FRAME_CLAUSES_V2.items():
        jobs.append((f"{name}_shot", f"{clause} AND {SHOT}"))
        jobs.append((f"{name}_adj", f"{clause} AND {ADJ}"))
    return jobs


# count-only consistency checks (not pulled; their content is the union of two pulled slices)
COUNT_ONLY = {
    "host9606_all4": f"host_tax_id=9606 AND {ALL4}",
    "tax3007725_shot_retired": f"tax_eq(3007725) AND {SHOT}",
}


def stream_pull(query, tag, fields=LEAN_FIELDS):
    """limit=0 pull, parsed in CHUNK-row pieces straight into a parquet file."""
    expected = HL.ena_count("read_run", query, purpose=f"enum_v2_count:{tag}")
    out_f = OUT / f"{tag}.parquet"
    if expected == 0:
        print(f"  [{tag}] expected 0 -- skipped", flush=True)
        return expected, 0
    t0 = time.time()
    tsv = HL.ena_search("read_run", query, fields, limit=0, purpose=f"enum_v2:{tag}")
    if not tsv or not tsv.strip():
        print(f"  [{tag}] EMPTY body (expected {expected})", flush=True)
        return expected, 0
    got, writer = 0, None
    schema = pa.schema([(c, pa.string()) for c in fields] + [("frame_query", pa.string())])
    for chunk in pd.read_csv(io.StringIO(tsv), sep="\t", dtype=str, on_bad_lines="skip",
                             low_memory=False, chunksize=CHUNK, keep_default_na=False):
        for c in fields:
            if c not in chunk:
                chunk[c] = ""
        chunk = chunk[fields].copy()
        chunk["frame_query"] = tag
        tbl = pa.Table.from_pandas(chunk, schema=schema, preserve_index=False)
        if writer is None:
            writer = pq.ParquetWriter(out_f, schema, compression="zstd")
        writer.write_table(tbl)
        got += len(chunk)
    if writer:
        writer.close()
    del tsv
    status = "OK" if expected == got else f"MISMATCH (expected {expected})"
    print(f"  [{tag}] rows={got:,} {status} {time.time()-t0:.0f}s", flush=True)
    return expected, got


def main(counts_only=False):
    v1 = {}
    try:
        a1 = pd.read_csv("enumeration_audit.csv")
        v1 = dict(zip(a1["tag"], a1["expected"]))
    except Exception:
        pass
    audit = []
    for tag, q in build_jobs():
        audit_f = OUT / f"{tag}.audit.json"
        if audit_f.exists() and (OUT / f"{tag}.parquet").exists() or \
           (audit_f.exists() and json.loads(audit_f.read_text()).get("got") == 0
            and json.loads(audit_f.read_text()).get("expected") == 0):
            a = json.loads(audit_f.read_text())
        elif counts_only:
            c = HL.ena_count("read_run", q, purpose=f"enum_v2_count:{tag}")
            a = {"slice": tag, "query": q, "count_v2": c, "got": None, "complete": None, "seconds": 0}
        else:
            t0 = time.time()
            expected, got = stream_pull(q, tag)
            a = {"slice": tag, "query": q, "count_v2": expected, "got": got,
                 "complete": expected == got, "seconds": round(time.time() - t0, 1)}
            audit_f.write_text(json.dumps(a))
        a["count_v1_if_any"] = v1.get(tag)
        a["pulled"] = True
        audit.append(a)
    for tag, q in COUNT_ONLY.items():
        c = HL.ena_count("read_run", q, purpose=f"enum_v2_count:{tag}")
        audit.append({"slice": tag, "query": q, "count_v2": c, "got": None, "complete": None,
                      "seconds": 0, "count_v1_if_any": v1.get(tag.replace("_retired", "")),
                      "pulled": False})
    cols = ["slice", "query", "count_v1_if_any", "count_v2", "got", "complete", "seconds", "pulled"]
    pd.DataFrame(audit)[cols].to_csv("enumeration_audit_v2.csv", index=False)
    inc = [a for a in audit if a["pulled"] and not a["complete"]]
    print(f"\nAudit: {len(audit)} slices, {len(inc)} incomplete", flush=True)
    for a in inc:
        print(f"  INCOMPLETE {a['slice']}: expected {a['count_v2']} got {a['got']}", flush=True)
    if counts_only:
        return

    # ---- union across slices, dedupe by run, keep provenance ----------------
    files = sorted(OUT.glob("*.parquet"))
    prov = {}
    for f in files:
        t = pq.read_table(f, columns=["run_accession", "frame_query"]).to_pandas()
        tag = t["frame_query"].iloc[0]
        for r in t["run_accession"].values:
            prov.setdefault(r, []).append(tag)
    print(f"unique runs across slices: {len(prov):,}", flush=True)
    seen = set()
    schema = pa.schema([(c, pa.string()) for c in LEAN_FIELDS] + [("found_by_v2", pa.string())])
    w = pq.ParquetWriter("universe_runs_v2_full.parquet", schema, compression="zstd")
    for f in files:
        pf = pq.ParquetFile(f)
        for b in pf.iter_batches(batch_size=CHUNK):
            df = b.to_pandas()
            df = df[~df["run_accession"].isin(seen)]
            if not len(df):
                continue
            seen.update(df["run_accession"].values)
            df["found_by_v2"] = [";".join(sorted(set(prov[r]))) for r in df["run_accession"]]
            df = df.drop(columns=["frame_query"])
            w.write_table(pa.Table.from_pandas(df, schema=schema, preserve_index=False))
    w.close()
    print(f"UNIQUE runs written: {len(seen):,}", flush=True)


if __name__ == "__main__":
    main(counts_only="--counts-only" in sys.argv)

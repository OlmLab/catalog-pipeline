"""
Step 2 -- exhaustive enumeration of the human DNA-shotgun metagenome universe.

Two-stage by design:
  Stage A (this script): pull RUN-level records across the whole frame with a
      lean field set, aggregate to study level locally.
  Stage B (later): full 83-field records + BioSample attributes, pulled only for
      studies that survive triage.

Why local aggregation is the only correct path (both verified live): ENA's
read_study result returns one row per RUN when filtered on run-level fields, and
the sample result rejects run-level filters outright.

Why limit=0 and not paging: ENA's `offset` parameter is broken for this endpoint
-- a request at offset=50000 returns an empty body rather than the next page,
which silently truncated an earlier run of this script at exactly 50,000 rows per
query. limit=0 streams the complete set and returned exactly 342,438 rows for
tax_eq(408170), matching the count endpoint. Every pull is therefore checked
against the count endpoint and the delta recorded, so truncation cannot pass
unnoticed again.

Frame = union of gut/linked metagenome taxa AND human-host metagenomic deposits,
crossed with in-scope shotgun strategies plus the adjudication strategies (OTHER,
Targeted-Capture) which are kept separate rather than silently dropped.
"""
import io
import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, ".")
import harvest_lib as HL
import scope_constants as SC

OUT = Path("enum"); OUT.mkdir(exist_ok=True)

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

SHOT = SC.ena_shotgun_clause()
ADJ = 'library_source="METAGENOMIC" AND (library_strategy="OTHER" OR library_strategy="Targeted-Capture")'


def full_pull(query, tag, fields=LEAN_FIELDS):
    expected = HL.ena_count("read_run", query, purpose=f"enum_count:{tag}")
    tsv = HL.ena_search("read_run", query, fields, limit=0, purpose=f"enum:{tag}")
    if not tsv or not tsv.strip():
        print(f"  [{tag}] EMPTY (expected {expected})", flush=True)
        return pd.DataFrame(columns=fields), expected, 0
    df = pd.read_csv(io.StringIO(tsv), sep="\t", dtype=str,
                     on_bad_lines="skip", low_memory=False)
    df["frame_query"] = tag
    status = "OK" if expected == len(df) else f"MISMATCH (expected {expected})"
    print(f"  [{tag}] rows={len(df):,} {status}", flush=True)
    return df, expected, len(df)


def main():
    jobs = []
    for tax in sorted(SC.TAXA_ALL_FRAME):
        jobs.append((f"tax{tax}_shot", f"tax_eq({tax}) AND {SHOT}"))
        jobs.append((f"tax{tax}_adj", f"tax_eq({tax}) AND {ADJ}"))
    jobs.append(("host9606_shot", f"host_tax_id=9606 AND {SHOT}"))
    jobs.append(("host9606_adj", f"host_tax_id=9606 AND {ADJ}"))
    jobs.append(("tax9606_shot", f"tax_eq(9606) AND {SHOT}"))

    all_frames, audit = [], []
    for tag, q in jobs:
        cache_f, audit_f = OUT / f"{tag}.parquet", OUT / f"{tag}.audit.json"
        if cache_f.exists() and audit_f.exists():
            df, a = pd.read_parquet(cache_f), json.loads(audit_f.read_text())
        elif audit_f.exists() and json.loads(audit_f.read_text())["got"] == 0:
            df, a = pd.DataFrame(), json.loads(audit_f.read_text())
        else:
            t0 = time.time()
            df, expected, got = full_pull(q, tag)
            a = {"tag": tag, "query": q, "expected": expected, "got": got,
                 "complete": expected == got, "seconds": round(time.time() - t0, 1)}
            if len(df):
                df.to_parquet(cache_f, index=False)
            audit_f.write_text(json.dumps(a))
        audit.append(a)
        if len(df):
            all_frames.append(df)

    pd.DataFrame(audit).to_csv("enumeration_audit.csv", index=False)
    incomplete = [a for a in audit if not a["complete"]]
    print(f"\nEnumeration audit: {len(audit)-len(incomplete)}/{len(audit)} queries complete",
          flush=True)
    for a in incomplete:
        print(f"  INCOMPLETE {a['tag']}: expected {a['expected']} got {a['got']}", flush=True)

    runs = pd.concat(all_frames, ignore_index=True)
    prov = (runs.groupby("run_accession")["frame_query"]
                .apply(lambda s: ";".join(sorted(set(s)))).rename("found_by"))
    runs = runs.drop_duplicates(subset=["run_accession"]).set_index("run_accession")
    runs["found_by"] = prov
    runs = runs.reset_index().drop(columns=["frame_query"])

    runs.to_parquet("universe_runs_lean.parquet", index=False)
    print(f"\nrows with overlap: {sum(len(f) for f in all_frames):,}")
    print(f"UNIQUE runs    : {len(runs):,}")
    print(f"UNIQUE studies : {runs.study_accession.nunique():,}")
    print(f"UNIQUE samples : {runs.sample_accession.nunique():,}")


if __name__ == "__main__":
    main()

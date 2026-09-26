#!/usr/bin/env python
"""prepare_inputs.py — derive the four intermediate tables build_sandpiper_tables.py reads from sp/ (R3-4).

RECONSTRUCTION NOTICE: in the 2026-09 build these four files were produced by inline root-session code that was not
saved as an artifact. This script rebuilds them from the archived inputs listed in config/inputs.json (group
`sandpiper`) and the current data package; column semantics follow build_sandpiper_tables.py's read sites and
sandpiper_flag_table.csv. Treat outputs as provisional until a rebuild reproduces the shipped sandpiper_* tables.

    python -m catalog.sandpiper.prepare_inputs --match data/inputs/sandpiper/catalog_runs_sandpiper_match.parquet \
        --per-acc data/inputs/sandpiper/sandpiper2.0.0.per_acc_summary.csv.gz --package data/inputs/data_package \
        --runs data/inputs/data_package/runs.parquet --out sp

Writes sp/matched_runs.parquet (run_accession, catalog_sample_key, study_accession, sample_unit — in_sandpiper only),
sp/sample_run_totals.parquet (catalog_sample_key, n_runs_total), sp/sample_scope.parquet (sample_key, study_accession,
infant_scope, n_samples_study) and sp/run_qc_input.parquet (run_accession + per_acc_summary QC fields + sp_flag_*).
"""
from __future__ import annotations

import argparse
import os
import re

import pandas as pd

RNA_STRATEGIES = {"RNA-Seq", "miRNA-Seq", "FL-cDNA", "ssRNA-seq", "ncRNA-Seq", "RIP-Seq", "Ribo-seq", "EST"}
RNA_SOURCES_STRICT = {"METATRANSCRIPTOMIC", "TRANSCRIPTOMIC", "TRANSCRIPTOMIC SINGLE CELL"}
RNA_SOURCES_LOOSE = RNA_SOURCES_STRICT | {"OTHER", "SYNTHETIC"}
COMMUNITY = re.compile(r"uncultured|environmental sample|enrichment culture|mixed culture|microbial community|consortium|microbiome", re.I)
PLACEHOLDER = re.compile(r"^(?:bacterium|unidentified|archaeon|prokaryote|eukaryote|organism|microorganism)\b", re.I)
INFANT_SCOPES = {"infant_evidenced", "study_all_infant"}  # age_scope values counted as in-scope for panels (F9 catalog_scope also excludes body-site excluded/linked)


def flags(df: pd.DataFrame) -> pd.DataFrame:
    org = df["organism"].fillna("").astype(str)
    strat = df.get("library_strategy", pd.Series([None] * len(df), index=df.index)).fillna("").astype(str)
    src = df.get("library_source", pd.Series([None] * len(df), index=df.index)).fillna("").astype(str).str.upper()
    has_mg = org.str.contains("metagenome", case=False)
    community = org.str.contains(COMMUNITY)
    placeholder = org.str.contains(PLACEHOLDER)
    out = pd.DataFrame(index=df.index)
    out["sp_flag_non_metagenome_strict"] = (~has_mg) & (~community) & (~placeholder) & (org != "")
    out["sp_flag_non_metagenome_loose"] = (~has_mg) & (~community) & (org != "")
    out["sp_flag_synthetic"] = org.str.contains(r"synthetic|simulat", case=False) | (src == "SYNTHETIC")
    out["sp_flag_rna_strict"] = strat.isin(RNA_STRATEGIES) | src.isin(RNA_SOURCES_STRICT)
    out["sp_flag_rna_loose"] = strat.isin(RNA_STRATEGIES) | src.isin(RNA_SOURCES_LOOSE)
    out["sp_flag_low_complexity"] = df["low_complexity"].astype(str).str.lower().eq("yes")
    out["sp_flag_readfraction_warning"] = df["warning"].notna() & df["warning"].astype(str).str.strip().ne("")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--match", required=True, help="catalog_runs_sandpiper_match.parquet")
    ap.add_argument("--per-acc", required=True, help="sandpiper<ver>.per_acc_summary.csv.gz")
    ap.add_argument("--package", required=True, help="unpacked data package dir (sample_metadata_wide.parquet, runs.parquet)")
    ap.add_argument("--runs", default=None, help="runs table with run_accession, library_strategy, library_source (default <package>/runs.parquet)")
    ap.add_argument("--out", default="sp")
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)

    m = pd.read_parquet(a.match)
    matched = m[m["in_sandpiper"]][["run_accession", "catalog_sample_key", "study_accession", "sample_unit"]].drop_duplicates("run_accession")
    matched.to_parquet(os.path.join(a.out, "matched_runs.parquet"), index=False)
    tot = m.groupby("catalog_sample_key").size().rename("n_runs_total").reset_index()
    tot.to_parquet(os.path.join(a.out, "sample_run_totals.parquet"), index=False)

    sw = pd.read_parquet(os.path.join(a.package, "sample_metadata_wide.parquet"), columns=["sample_key", "study_accession", "age_scope"])
    sw["infant_scope"] = sw["age_scope"].isin(INFANT_SCOPES)
    sw["n_samples_study"] = sw.groupby("study_accession")["sample_key"].transform("size")
    sw[["sample_key", "study_accession", "infant_scope", "n_samples_study"]].to_parquet(os.path.join(a.out, "sample_scope.parquet"), index=False)

    keep = set(matched["run_accession"])
    parts = []
    for chunk in pd.read_csv(a.per_acc, chunksize=500_000, dtype={"sample": "string"}):
        parts.append(chunk[chunk["sample"].isin(keep)])
    qc = pd.concat(parts, ignore_index=True).rename(columns={"sample": "run_accession"})
    runs_p = a.runs or os.path.join(a.package, "runs.parquet")
    if os.path.exists(runs_p):
        cols = [c for c in ("run_accession", "library_strategy", "library_source") if c in pd.read_parquet(runs_p).columns]
        qc = qc.merge(pd.read_parquet(runs_p, columns=cols).drop_duplicates("run_accession"), on="run_accession", how="left")
    qc["sp_spf"] = qc["singlem_prokaryotic_fraction"]
    qc["sp_known_species_fraction"] = qc["known_species_fraction"]
    qc = pd.concat([qc, flags(qc)], axis=1)
    qc.to_parquet(os.path.join(a.out, "run_qc_input.parquet"), index=False)
    print({"matched_runs": len(matched), "sample_run_totals": len(tot), "sample_scope": len(sw), "run_qc_input": len(qc),
           "runs_without_qc": int(len(keep) - qc["run_accession"].nunique())})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

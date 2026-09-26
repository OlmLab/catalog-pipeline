"""Fill + normalise SingleM 'condensed' (unfilled) profiles to per-rank relative abundance.

Definitions (Reviewer B §3):
  unfilled coverage  = coverage assigned exactly to a node (excludes descendants)   -- what the Zenodo bulk file holds
  filled coverage    = unfilled coverage of the node + all of its descendants       -- 'full_coverage' in Sandpiper's with-extras file
  root (filled)      = sum of all unfilled coverage of the profile (d__Bacteria + d__Archaea)
  rel_abundance(node)= filled(node) / root
  unassigned_at_<rank> = root - sum(filled at that rank) = coverage that stopped at a shallower rank
Aggregation to the catalog sample unit (A16/B6): SUM unfilled coverage per taxon across the sample's profiled runs,
then fill and normalise (equivalent to profiling concatenated reads, up to SingleM's per-run 0.35x noise floor).
"""
import re
import pandas as pd
import numpy as np

RANKS = ["domain", "phylum", "class", "order", "family", "genus", "species"]
RANK_PREFIX = dict(zip(RANKS, ["d__", "p__", "c__", "o__", "f__", "g__", "s__"]))
SEP = "; "


def split_lineage(tax: str):
    """'Root; d__Bacteria; p__X' -> ['d__Bacteria','p__X'] (drops the Root token)."""
    parts = [p.strip() for p in tax.split(";")]
    return [p for p in parts if p and p != "Root"]


def fill_profile(df: pd.DataFrame, key="sample", tax="taxonomy", cov="coverage") -> pd.DataFrame:
    """Expand unfilled rows to every ancestor prefix and sum -> filled coverage per (key, rank, taxon).
    Returns columns: key, rank (str), rank_i (1..7), taxon (last token), lineage (full prefix string), coverage_filled.
    Vectorised: explode prefixes."""
    d = df[[key, tax, cov]].copy()
    d["_lev"] = d[tax].map(split_lineage)
    d = d[d["_lev"].map(len) > 0]
    d["_n"] = d["_lev"].map(len)
    # explode to ancestors
    rows = []
    for n in range(1, 8):
        sub = d[d["_n"] >= n]
        if sub.empty:
            continue
        pref = sub["_lev"].map(lambda L: SEP.join(L[:n]))
        rows.append(pd.DataFrame({key: sub[key].values, "rank_i": n, "lineage": pref.values, "coverage_filled": sub[cov].values}))
    out = pd.concat(rows, ignore_index=True)
    out = out.groupby([key, "rank_i", "lineage"], as_index=False, sort=False)["coverage_filled"].sum()
    out["rank"] = out["rank_i"].map(lambda i: RANKS[i - 1])
    out["taxon"] = out["lineage"].str.rsplit(SEP, n=1).str[-1]
    return out


def normalise(filled: pd.DataFrame, key="sample") -> pd.DataFrame:
    """Add root coverage, rel_abundance and unassigned_at_<rank> rows. Root = sum of domain-level filled coverage."""
    root = filled[filled.rank_i == 1].groupby(key)["coverage_filled"].sum().rename("root_coverage")
    f = filled.merge(root, left_on=key, right_index=True, how="left")
    assigned = f.groupby([key, "rank_i"], as_index=False)["coverage_filled"].sum().merge(root, left_on=key, right_index=True)
    assigned["coverage_filled"] = (assigned["root_coverage"] - assigned["coverage_filled"]).clip(lower=0)
    un = assigned[assigned["coverage_filled"] > 1e-9].copy()
    un["rank"] = un["rank_i"].map(lambda i: RANKS[i - 1])
    un["taxon"] = "unassigned_at_" + un["rank"]
    un["lineage"] = un["taxon"]
    f = pd.concat([f, un[f.columns]], ignore_index=True)
    f["rel_abundance"] = np.where(f["root_coverage"] > 0, f["coverage_filled"] / f["root_coverage"], np.nan)
    return f


def shannon(p: np.ndarray) -> float:
    p = p[p > 0]
    return float(-(p * np.log(p)).sum()) if p.size else np.nan


def bray_curtis(a: pd.Series, b: pd.Series) -> float:
    """a, b: rel-abundance Series indexed by taxon (genus incl. unassigned)."""
    idx = a.index.union(b.index)
    x = a.reindex(idx, fill_value=0.0).values
    y = b.reindex(idx, fill_value=0.0).values
    s = x.sum() + y.sum()
    return float(np.abs(x - y).sum() / s) if s > 0 else np.nan

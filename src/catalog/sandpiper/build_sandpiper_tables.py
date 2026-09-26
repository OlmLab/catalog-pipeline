"""Build all Sandpiper deliverables from sp/sandpiper_profiles_runs_raw.parquet (run, coverage_filled, taxonomy).
Steps: (1) run-level table with derived unfilled coverage; (2) aggregate FILLED coverage to the catalog sample unit by SUM
across profiled runs (fill is linear, so sum-of-filled == filled-of-sum); (3) normalise per rank with unassigned_at_<rank>;
(4) run-concordance (genus Bray-Curtis) for multi-run samples; (5) sample summary + indicators; (6) top genera, bifido
species, study panels. Everything deterministic; DuckDB for the heavy joins."""
import duckdb, pandas as pd, numpy as np, json, time, os, re
t0 = time.time()
con = duckdb.connect()
con.execute("PRAGMA threads=8; PRAGMA memory_limit='24GB';")
TAXDB = os.environ.get("SANDPIPER_TAXDB", "GTDB"); TAXVER = os.environ.get("SANDPIPER_TAXVER", "R232")  # shim 2026-09-26 (R3-4)
SPVER = os.environ.get("SANDPIPER_VERSION", "2.0.0"); ZEN = os.environ.get("SANDPIPER_ZENODO_RECORD", "20419175")
RANKS = ["root", "domain", "phylum", "class", "order", "family", "genus", "species"]

con.execute("""CREATE TABLE raw AS SELECT run, coverage_filled, taxonomy,
    length(taxonomy) - length(replace(taxonomy, ';', '')) AS rank_i,
    CASE WHEN taxonomy = 'Root' THEN NULL ELSE regexp_replace(taxonomy, ';\\s*[^;]+$', '') END AS parent
  FROM read_parquet('sp/sandpiper_profiles_runs_raw.parquet')""")
n_raw = con.execute("SELECT count(*), count(DISTINCT run) FROM raw").fetchone()
print("raw rows/runs", n_raw, flush=True)

# (1) run-level with unfilled coverage
con.execute("""CREATE TABLE runlevel AS
  SELECT r.run, r.taxonomy, r.rank_i, r.coverage_filled,
         round(r.coverage_filled - coalesce(c.child_sum, 0), 4) AS coverage_unfilled
  FROM raw r LEFT JOIN (SELECT run, parent, sum(coverage_filled) AS child_sum FROM raw WHERE parent IS NOT NULL GROUP BY run, parent) c
    ON c.run = r.run AND c.parent = r.taxonomy""")
neg = con.execute("SELECT count(*) FROM runlevel WHERE coverage_unfilled < -0.02").fetchone()[0]
print("negative unfilled (rounding) rows:", neg, flush=True)
con.execute(f"""COPY (SELECT run, taxonomy, rank_i, coverage_filled, coverage_unfilled,
   '{TAXDB}' AS taxonomy_db, '{TAXVER}' AS taxonomy_version, '{SPVER}' AS sandpiper_version, '{ZEN}' AS zenodo_record
   FROM runlevel ORDER BY run, rank_i, taxonomy) TO 'sp/sandpiper_profiles_runs.parquet' (FORMAT PARQUET, COMPRESSION ZSTD)""")
print("runlevel written", time.time() - t0, flush=True)

# (2) aggregate to catalog sample unit
con.execute("CREATE TABLE m AS SELECT run_accession AS run, catalog_sample_key AS sample_key, study_accession, sample_unit FROM read_parquet('sp/matched_runs.parquet') WHERE run_accession IN (SELECT DISTINCT run FROM raw)")
n_m = con.execute("SELECT count(*), count(DISTINCT sample_key) FROM m").fetchone(); print("matched runs with profiles / sample keys:", n_m, flush=True)
con.execute("""CREATE TABLE agg AS
  SELECT m.sample_key, r.taxonomy, r.rank_i, sum(r.coverage_filled) AS coverage_filled
  FROM raw r JOIN m ON m.run = r.run GROUP BY m.sample_key, r.taxonomy, r.rank_i""")
con.execute("CREATE TABLE root AS SELECT sample_key, coverage_filled AS root_coverage FROM agg WHERE rank_i = 0")
# (3) normalise + unassigned rows
con.execute("""CREATE TABLE prof AS
  SELECT a.sample_key, a.rank_i, a.taxonomy AS lineage,
         regexp_replace(a.taxonomy, '^.*;\\s*', '') AS taxon,
         a.coverage_filled, CASE WHEN r.root_coverage > 0 THEN a.coverage_filled / r.root_coverage END AS rel_abundance
  FROM agg a JOIN root r USING (sample_key) WHERE a.rank_i > 0
  UNION ALL
  SELECT s.sample_key, s.rank_i, 'unassigned_at_' || s.rank_name AS lineage, 'unassigned_at_' || s.rank_name AS taxon,
         s.unassigned, CASE WHEN s.root_coverage > 0 THEN s.unassigned / s.root_coverage END
  FROM (SELECT r.sample_key, g.rank_i, g.rank_name, r.root_coverage,
               greatest(r.root_coverage - coalesce(sum(a.coverage_filled), 0), 0) AS unassigned
        FROM root r CROSS JOIN (SELECT * FROM (VALUES (1,'domain'),(2,'phylum'),(3,'class'),(4,'order'),(5,'family'),(6,'genus'),(7,'species')) t(rank_i, rank_name)) g
        LEFT JOIN agg a ON a.sample_key = r.sample_key AND a.rank_i = g.rank_i
        GROUP BY r.sample_key, g.rank_i, g.rank_name, r.root_coverage) s
  WHERE s.unassigned > 1e-6""")
con.execute(f"""COPY (SELECT sample_key, (['root','domain','phylum','class','order','family','genus','species'])[rank_i+1] AS rank, taxon, lineage,
   round(coverage_filled, 4) AS coverage_filled, round(rel_abundance, 6) AS rel_abundance,
   '{TAXDB}' AS taxonomy_db, '{TAXVER}' AS taxonomy_version, '{SPVER}' AS sandpiper_version
   FROM prof ORDER BY sample_key, rank_i, rel_abundance DESC) TO 'sp/sandpiper_profiles.parquet' (FORMAT PARQUET, COMPRESSION ZSTD)""")
n_prof = con.execute("SELECT count(*), count(DISTINCT sample_key) FROM prof").fetchone(); print("profiles rows/samples", n_prof, time.time() - t0, flush=True)
# sanity: per rank, sum(rel_abundance) == 1
chk = con.execute("SELECT rank_i, min(s), max(s) FROM (SELECT sample_key, rank_i, sum(rel_abundance) s FROM prof GROUP BY 1,2) GROUP BY 1 ORDER BY 1").fetchall(); print("rank sums (min,max):", chk, flush=True)

# (4) run concordance at genus level (rel abundance per run incl. unassigned_at_genus)
con.execute("""CREATE TABLE rg AS
  SELECT r.run, m.sample_key, r.taxonomy AS lineage, r.coverage_filled / rt.root AS ra
  FROM raw r JOIN m USING (run) JOIN (SELECT run, coverage_filled AS root FROM raw WHERE rank_i = 0) rt USING (run)
  WHERE r.rank_i = 6 AND rt.root > 0
  UNION ALL
  SELECT rt.run, m.sample_key, 'unassigned_at_genus', greatest(rt.root - coalesce(g.s, 0), 0) / rt.root
  FROM (SELECT run, coverage_filled AS root FROM raw WHERE rank_i = 0) rt JOIN m USING (run)
  LEFT JOIN (SELECT run, sum(coverage_filled) s FROM raw WHERE rank_i = 6 GROUP BY run) g USING (run) WHERE rt.root > 0""")
multi = con.execute("""SELECT sample_key FROM m GROUP BY sample_key HAVING count(*) > 1""").df()["sample_key"].tolist()
print("multi-run profiled samples:", len(multi), flush=True)
rgdf = con.execute("SELECT * FROM rg WHERE sample_key IN (SELECT sample_key FROM m GROUP BY sample_key HAVING count(*) > 1)").df()
conc_rows = []
for sk, d in rgdf.groupby("sample_key"):
    piv = d.pivot_table(index="lineage", columns="run", values="ra", aggfunc="sum", fill_value=0.0)
    X = piv.values; runs_ = list(piv.columns)
    if len(runs_) < 2:
        continue
    bcs = []
    for i in range(len(runs_)):
        for j in range(i + 1, len(runs_)):
            s = X[:, i].sum() + X[:, j].sum()
            bcs.append(np.abs(X[:, i] - X[:, j]).sum() / s if s > 0 else np.nan)
    conc_rows.append({"sample_key": sk, "n_runs_profiled": len(runs_), "bc_genus_max": float(np.nanmax(bcs)), "bc_genus_mean": float(np.nanmean(bcs)), "runs": ";".join(runs_)})
conc = pd.DataFrame(conc_rows)
conc.to_parquet("sp/sandpiper_run_concordance.parquet", index=False)
print("concordance computed", len(conc), "discordant(>0.5):", int((conc.bc_genus_max > 0.5).sum()), time.time() - t0, flush=True)

# (5) sample summary
qc = pd.read_parquet("sp/run_qc_input.parquet")  # run-level QC (per_acc_summary fields + flags) for matched runs
mdf = con.execute("SELECT * FROM m").df()
rq = mdf.merge(qc, left_on="run", right_on="run_accession", how="left")
rq["w"] = rq["bacterial_archaeal_bases"].fillna(0) / 1e6  # weight for read-fraction quantities: bacterial+archaeal bases (SPF uses read fraction; base-weighted)
rq["mg_mb"] = rq["metagenome_size"].fillna(0) / 1e6
g = rq.groupby("sample_key")
def wmean(col, w):
    def f(d):
        ww = d[w]; x = d[col]
        return float((x * ww).sum() / ww.sum()) if ww.sum() > 0 else float(x.mean())
    return f
summ = pd.DataFrame({
    "sp_n_runs_profiled": g["run"].size(),
    "sp_spf": g.apply(wmean("sp_spf", "mg_mb")),                   # SPF = prokaryotic fraction of all reads -> weight by metagenome size
    "sp_known_species_fraction": g.apply(wmean("sp_known_species_fraction", "w")),  # fraction of prokaryotic coverage -> weight by bacterial+archaeal bases
    "sp_flag_low_complexity": g["sp_flag_low_complexity"].apply(lambda s: bool(s.fillna(False).any())),
    "sp_flag_non_metagenome": g["sp_flag_non_metagenome_strict"].apply(lambda s: bool(s.fillna(False).any())),
    "sp_flag_synthetic": g["sp_flag_synthetic"].apply(lambda s: bool(s.fillna(False).any())),
    "sp_flag_rna": g["sp_flag_rna_strict"].apply(lambda s: bool(s.fillna(False).any())),
    "sp_flag_readfraction_warning": g["sp_flag_readfraction_warning"].apply(lambda s: bool(pd.Series(s).eq(True).any())),
    "sandpiper_url": g["run"].apply(lambda s: "https://sandpiper.qut.edu.au/run/" + sorted(s)[0]),
    "sp_runs_profiled": g["run"].apply(lambda s: ";".join(sorted(s))),
})
nt = pd.read_parquet("sp/sample_run_totals.parquet").set_index("catalog_sample_key")  # n_runs_total per catalog sample key
summ = summ.join(nt["n_runs_total"].rename("sp_n_runs_total"))
summ["sp_partial"] = summ.sp_n_runs_profiled < summ.sp_n_runs_total
summ = summ.join(con.execute("SELECT sample_key, root_coverage FROM root").df().set_index("sample_key")["root_coverage"].rename("sp_root_coverage"))
summ["sp_low_depth"] = summ.sp_root_coverage < 2
summ["sp_profiled"] = True
summ = summ.join(conc.set_index("sample_key")[["bc_genus_max"]].rename(columns={"bc_genus_max": "sp_run_concordance_bc"}))
summ["sp_runs_discordant"] = summ.sp_run_concordance_bc > 0.5

# indicators (GTDB R232 names)
def ra(where):
    return con.execute(f"SELECT sample_key, sum(rel_abundance) v FROM prof WHERE {where} GROUP BY 1").df().set_index("sample_key")["v"]
ENTERO_CORE = ["Escherichia", "Klebsiella", "Enterobacter", "Citrobacter", "Salmonella", "Serratia"]
ind = {
    "sp_ra_g_Bifidobacterium": ra("rank_i=6 AND taxon='g__Bifidobacterium'"),
    "sp_ra_f_Bacteroidaceae": ra("rank_i=5 AND taxon='f__Bacteroidaceae'"),
    "sp_ra_g_Bacteroides": ra("rank_i=6 AND taxon='g__Bacteroides'"),
    "sp_ra_g_Phocaeicola": ra("rank_i=6 AND taxon='g__Phocaeicola'"),
    "sp_ra_enterobacterales_core": ra("rank_i=6 AND taxon IN (" + ",".join(f"'g__{x}'" for x in ENTERO_CORE) + ")"),
    "sp_ra_g_Escherichia": ra("rank_i=6 AND taxon='g__Escherichia'"),
    "sp_ra_g_Klebsiella": ra("rank_i=6 AND taxon='g__Klebsiella'"),
    "sp_ra_f_Lachnospiraceae": ra("rank_i=5 AND taxon='f__Lachnospiraceae'"),
    "sp_ra_f_Lactobacillaceae": ra("rank_i=5 AND taxon='f__Lactobacillaceae'"),
    "sp_ra_g_Streptococcus": ra("rank_i=6 AND taxon='g__Streptococcus'"),
    "sp_ra_g_Staphylococcus": ra("rank_i=6 AND taxon='g__Staphylococcus'"),
    "sp_ra_g_Enterococcus": ra("rank_i=6 AND taxon='g__Enterococcus'"),
    "sp_ra_g_Veillonella": ra("rank_i=6 AND taxon='g__Veillonella'"),
    "sp_ra_g_Clostridioides": ra("rank_i=6 AND taxon='g__Clostridioides'"),
    "sp_ra_unassigned_genus": ra("rank_i=6 AND taxon='unassigned_at_genus'"),
    "sp_ra_unassigned_species": ra("rank_i=7 AND taxon='unassigned_at_species'"),
}
for k, v in ind.items():
    summ[k] = v.reindex(summ.index).fillna(0.0)
# top genus, shannon (genus incl. unassigned bin), n_genera >=1%
gen = con.execute("SELECT sample_key, taxon, rel_abundance FROM prof WHERE rank_i = 6").df()
top = gen.sort_values(["sample_key", "rel_abundance"], ascending=[True, False]).drop_duplicates("sample_key").set_index("sample_key")
summ["sp_top_genus"] = top["taxon"].reindex(summ.index); summ["sp_top_genus_ra"] = top["rel_abundance"].reindex(summ.index)
def sh(s):
    p = s.values; p = p[p > 0]; return float(-(p * np.log(p)).sum())
summ["sp_shannon_genus"] = gen.groupby("sample_key")["rel_abundance"].apply(sh).reindex(summ.index)
summ["sp_n_genera_ge1pct"] = gen[(gen.rel_abundance >= 0.01) & (~gen.taxon.str.startswith("unassigned"))].groupby("sample_key").size().reindex(summ.index).fillna(0).astype(int)
summ["taxonomy_db"] = TAXDB; summ["taxonomy_version"] = TAXVER; summ["sandpiper_version"] = SPVER; summ["zenodo_record"] = ZEN
summ = summ.reset_index()
summ.to_parquet("sp/sandpiper_sample_summary.parquet", index=False)
print("sample summary", summ.shape, time.time() - t0, flush=True)

# (6) top-15 genera per sample (on-site), bifido species, study panels
top15 = gen[~gen.taxon.str.startswith("unassigned")].sort_values(["sample_key", "rel_abundance"], ascending=[True, False]).groupby("sample_key").head(15)
top15 = pd.concat([top15, gen[gen.taxon == "unassigned_at_genus"]]).sort_values(["sample_key", "rel_abundance"], ascending=[True, False])
top15["rel_abundance"] = top15.rel_abundance.round(5)
top15.to_parquet("sp/sandpiper_top_genera.parquet", index=False)
bif = con.execute("""SELECT sample_key, taxon AS species, round(coverage_filled,4) AS coverage_filled, round(rel_abundance,6) AS rel_abundance,
   round(rel_abundance / nullif(sum(rel_abundance) OVER (PARTITION BY sample_key), 0), 6) AS share_within_bifidobacterium
   FROM prof WHERE rank_i = 7 AND lineage LIKE '%g__Bifidobacterium; s__%' ORDER BY sample_key, rel_abundance DESC""").df()
bif["taxonomy_db"] = TAXDB; bif["taxonomy_version"] = TAXVER
bif.to_parquet("sp/sandpiper_bifidobacterium_species.parquet", index=False)
print("top15", top15.shape, "bifido species", bif.shape, bif.species.nunique(), flush=True)

# study panels: mean rel_abundance over profiled infant-scope samples; top-12 phyla, top-15 genera per study
scope = pd.read_parquet("sp/sample_scope.parquet")  # sample_key, study_accession, infant_scope(bool), n_samples_study
prof_sk = con.execute("SELECT DISTINCT sample_key FROM root").df()["sample_key"]
sc = scope[scope.sample_key.isin(set(prof_sk)) & scope.infant_scope]
con.register("sc", sc[["sample_key", "study_accession"]])
panel = con.execute("""
  WITH x AS (SELECT sc.study_accession, p.rank_i, p.taxon, sum(p.rel_abundance) / n.n AS mean_ra, n.n AS n_samples
             FROM prof p JOIN sc USING (sample_key)
             JOIN (SELECT study_accession, count(*) n FROM sc GROUP BY 1) n USING (study_accession)
             WHERE p.rank_i IN (2, 6) GROUP BY 1, 2, 3, n.n),
  r AS (SELECT *, row_number() OVER (PARTITION BY study_accession, rank_i ORDER BY mean_ra DESC) AS rk FROM x WHERE taxon NOT LIKE 'unassigned_at_%')
  SELECT study_accession, CASE rank_i WHEN 2 THEN 'phylum' ELSE 'genus' END AS rank, taxon, round(mean_ra, 6) AS mean_rel_abundance, n_samples, rk AS rank_order
  FROM r WHERE (rank_i = 2 AND rk <= 12) OR (rank_i = 6 AND rk <= 15)
  UNION ALL
  SELECT study_accession, CASE rank_i WHEN 2 THEN 'phylum' ELSE 'genus' END, taxon, round(mean_ra, 6), n_samples, 0 FROM x WHERE taxon LIKE 'unassigned_at_%'
  ORDER BY study_accession, rank, rank_order""").df()
studytot = scope.groupby("study_accession").agg(n_samples=("sample_key", "size"), n_infant_scope=("infant_scope", "sum"))
studytot["n_profiled"] = scope[scope.sample_key.isin(set(prof_sk))].groupby("study_accession").size().reindex(studytot.index).fillna(0).astype(int)
studytot["n_profiled_infant_scope"] = sc.groupby("study_accession").size().reindex(studytot.index).fillna(0).astype(int)
studytot["frac_samples_profiled"] = studytot.n_profiled / studytot.n_samples
panel = panel.merge(studytot.reset_index()[["study_accession", "n_samples", "n_infant_scope", "n_profiled", "frac_samples_profiled"]], on="study_accession", how="left")
panel["taxonomy_db"] = TAXDB; panel["taxonomy_version"] = TAXVER
panel.to_parquet("sp/sandpiper_study_panels.parquet", index=False)
studytot.reset_index().to_parquet("sp/sandpiper_study_profiled_counts.parquet", index=False)
print("study panels", panel.shape, panel.study_accession.nunique(), time.time() - t0, flush=True)
sizes = {f: os.path.getsize(f"sp/{f}") for f in os.listdir("sp") if f.startswith("sandpiper_") and (f.endswith(".parquet") or f.endswith(".csv"))}
json.dump({"raw": n_raw, "profiles": n_prof, "rank_sums": chk, "negative_unfilled_rows": neg, "multi_run_profiled_samples": len(multi), "discordant": int((conc.bc_genus_max > 0.5).sum()), "sizes": sizes, "seconds": round(time.time() - t0, 1)}, open("sp/build_log.json", "w"), indent=1, default=str)
print(json.dumps(sizes, indent=1), flush=True)

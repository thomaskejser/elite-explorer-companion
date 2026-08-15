"""De-bias the BH/WR expected counts.

True Forge rate pi(mass_code, radius) is estimated from WELL-SAMPLED boxels
(>=10 scanned AND >=80% of pop scanned) where the scanned set ~= the full
population, so the BH/WR rate is unbiased. We interpolate pi across galactocentric
radius (it declines with radius) and apply it to the missing systems, replacing
the selection-biased model score.

De-biased expected undiscovered = missing_systems * pi(mass_code, plane_r).
"""
import duckdb, pathlib, numpy as np
con = duckdb.connect(str(pathlib.Path(__file__).resolve().parent.parent / "elite_mapping.duckdb"))
con.execute("SET memory_limit='7GB'"); con.execute("SET threads=8")

KBASE = r"regexp_replace(name,'[0-9]+(-[0-9]+)?$','')"
TOK   = r"regexp_extract(name,'([0-9]+(-[0-9]+)?)$',1)"
BOXEL = f"CASE WHEN {TOK} LIKE '%-%' THEN {KBASE}||'#'||split_part({TOK},'-',1) ELSE {KBASE} END"
IDX   = f"CASE WHEN {TOK} LIKE '%-%' THEN CAST(split_part({TOK},'-',2) AS BIGINT) ELSE CAST({TOK} AS BIGINT) END"

con.execute(f"""
CREATE OR REPLACE TEMP TABLE boxstat AS
SELECT {BOXEL} AS boxel, mass_code, avg(plane_r) plane_r,
       max({IDX})+1 AS pop, count(*) FILTER (WHERE is_scanned) AS scanned,
       sum(has_bh) FILTER (WHERE is_scanned) AS bh, sum(has_wr) FILTER (WHERE is_scanned) AS wr,
       sum(missing_flag) AS missing
FROM (SELECT *, (NOT is_scanned)::int AS missing_flag FROM sys_feat
      WHERE mass_code IN ('f','g','h') AND {TOK} <> '')
GROUP BY 1,2
""")

# well-sampled = genuinely near-complete boxels -> unbiased rate.
# Pool f/g/h for a STABLE radial BH curve (all high-mass codes have similar core
# rates; f alone is too sparsely fully-sampled). WR uses h only.
BAND = 2500
def rate_curve(target, mcs):
    inlist = ",".join(f"'{m}'" for m in mcs)
    rows = con.execute(f"""
        SELECT floor(plane_r/{BAND})*{BAND} AS band, sum({target}) t, sum(scanned) sc
        FROM boxstat WHERE mass_code IN ({inlist}) AND scanned>=10 AND scanned >= 0.8*pop
        GROUP BY 1 HAVING sum(scanned) >= 200 ORDER BY 1
    """).fetchall()
    x  = np.array([r[0]+BAND/2 for r in rows], float)
    pi = np.array([r[1]/r[2]   for r in rows], float)
    return x, pi, [(int(r[0]), int(r[2]), round(100*r[1]/r[2],2)) for r in rows]

def interp_pi(x_knots, pi_knots, xq):
    if len(x_knots) == 0: return np.zeros_like(xq)
    return np.interp(xq, x_knots, pi_knots, left=pi_knots[0], right=pi_knots[-1])

print("=== de-biased true-rate curve pi(radius) from well-sampled boxels ===")
xb, pib, tbl_bh = rate_curve("bh", ["f","g","h"])
xw, piw, tbl_wr = rate_curve("wr", ["h"])
print("\n BH (f/g/h pooled): band_kly -> true_rate% (n_scanned)")
print("   " + "  ".join(f"{int(b/1000)}:{p}%(n={n:,})" for b,n,p in tbl_bh))
print("\n WR (mass h): band_kly -> true_rate% (n_scanned)")
print("   " + "  ".join(f"{int(b/1000)}:{p}%(n={n:,})" for b,n,p in tbl_wr))

# Apply pi to the SAME theorised-missing counts the biased numbers used.
bx = con.execute("""SELECT boxel, mass_code, plane_r, missing,
                    sector, exp_bh AS exp_bh_biased, exp_wr AS exp_wr_biased
                    FROM theorised_boxels""").df()
pr = bx.plane_r.values.astype(float)
pi_bh = interp_pi(xb, pib, pr)
pi_wr = np.where(bx.mass_code.values=='h', interp_pi(xw, piw, pr), 0.0)
bx["deb_exp_bh"] = bx.missing.values * pi_bh
bx["deb_exp_wr"] = bx.missing.values * pi_wr

def totals(mask, name):
    d = bx[mask]
    print(f"  {name:20s} biased E[BH]={d.exp_bh_biased.sum():>12,.0f}  debiased E[BH]={d.deb_exp_bh.sum():>11,.0f}"
          f"   biased E[WR]={d.exp_wr_biased.sum():>9,.0f}  debiased E[WR]={d.deb_exp_wr.sum():>8,.0f}")
print("\n=== biased vs DE-BIASED expected undiscovered ===")
totals(bx.plane_r.notna(), "whole galaxy f/g/h")
totals(bx.plane_r>30000, "fringe (>30 kly)")

# persist de-biased fringe sector table
fr = bx[bx.plane_r>30000].groupby("sector").agg(
    theorised=("missing","sum"), exp_bh_biased=("exp_bh_biased","sum"),
    deb_exp_bh=("deb_exp_bh","sum"), exp_wr_biased=("exp_wr_biased","sum"),
    deb_exp_wr=("deb_exp_wr","sum"), plane_r=("plane_r","mean")).reset_index()
fr = fr[fr.theorised>=10]
con.register("fr_df", fr)
con.execute("""CREATE OR REPLACE TABLE fringe_sectors_debiased AS
    SELECT f.sector, round(f.plane_r) plane_r_ly, f.theorised,
           round(f.exp_bh_biased,1) exp_bh_biased, round(f.deb_exp_bh,1) exp_bh_debiased,
           round(f.exp_wr_biased,1) exp_wr_biased, round(f.deb_exp_wr,1) exp_wr_debiased,
           s.found_bh, s.found_wr, s.x, s.y, s.z
    FROM fr_df f LEFT JOIN fringe_sectors s USING(sector)""")
con.unregister("fr_df")

print("\n=== TOP 15 FRINGE SECTORS by DE-BIASED expected black holes ===")
print(f"  {'sector':22}{'found_BH':>9}{'exp_BH_biased':>15}{'exp_BH_debiased':>16}{'theorised':>10}")
for r in con.execute("""SELECT sector, found_bh, exp_bh_biased, exp_bh_debiased, theorised
     FROM fringe_sectors_debiased ORDER BY exp_bh_debiased DESC LIMIT 15""").fetchall():
    print(f"  {str(r[0])[:20]:20s}{int(r[1] or 0):>9,}{r[2]:>15}{r[3]:>16}{int(r[4]):>10,}")
print("\n=== TOP 15 FRINGE SECTORS by DE-BIASED expected Wolf-Rayet ===")
print(f"  {'sector':22}{'found_WR':>9}{'exp_WR_biased':>15}{'exp_WR_debiased':>16}{'theorised':>10}")
for r in con.execute("""SELECT sector, found_wr, exp_wr_biased, exp_wr_debiased, theorised
     FROM fringe_sectors_debiased ORDER BY exp_wr_debiased DESC LIMIT 15""").fetchall():
    print(f"  {str(r[0])[:20]:20s}{int(r[1] or 0):>9,}{r[2]:>15}{r[3]:>16}{int(r[4]):>10,}")
con.close()

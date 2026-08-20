"""Build `system_predicted` -- every system we can predict, with per-target probabilities.

DERIVED table (ETL.md): built from other DB tables, no input/ parquet, no loader.

BUILT ENTIRELY FROM THE NEW MODEL PLUS `staging`. Nothing here reads the legacy
prediction pipeline any more. What each dropped table used to supply, and what replaced
it -- every substitution validated against the original before the switch:

  sys_feat          -> system_known. Same systems and then some: 197.6M vs 194.7M,
                       because sys_feat was built from Spansh alone. mass_code, x/y/z
                       and the boxel structure are columns there; plane_r / r_sgra /
                       dist_sol are computed here from the same Sgr A* constants.
  bhwr_system       -> system_body JOIN body. has_bh/has_wr/has_neutron from body.code.
  star_agg          -> the same join. has_wd/has_herbig/has_otype/has_supergiant
                       reproduce the legacy labels EXACTLY -- 0 disagreements over
                       74,953,739 comparable systems. has_bh/has_wr/has_neutron are a
                       strict SUPERSET (+4,069 / +101 / +15,147, none lost), because
                       system_body now carries the EDAstro full catalogues that
                       bhwr_system never saw.
  theorised_system  -> staging.pred_boxel_gap, recomputed here from system_known's
                       (sector_id, cube_id, mass_code, sub_cube_id, boxel_index) with
                       03s's rule intact: INTERNAL gaps only, and only in boxels where
                       observed >= 50% of the min..max index range. Yields 61,239
                       against the legacy 57,700 (f 14,027/13,782, g 14,901/14,097,
                       h 32,311/29,821) -- higher because system_known holds ~2.9M more
                       systems, so more boxels clear the density bar.
  bhwr_candidates   -> GONE, and with it the p_bh_model / p_wr_model columns. They came
                       from a gradient-boosted model in scripts/03c that this pipeline
                       cannot reproduce, so in a database built from the new model they
                       could only ever be NULL -- and a permanently-NULL column named
                       like a probability is a trap. The 03c table's own comment says
                       its RANKINGS are the trustworthy output and its absolute values
                       are biased upward; app/candidates.parquet already holds the
                       flight-calibrated levels the app uses.
  spansh_system     -> staging.spansh_system. RAW, kept: declared/scanned body counts
  edastro_boxel_stats  and published per-boxel helium have no substitute in the model.

*** WHAT COUNTS AS SCANNED. *** A system is in the rate DENOMINATOR only if it holds at
least one body row from a real scan (source not in edastro_rare / edastro_neutron /
canonn_codex) and at least one star. Catalogue-only systems are excluded on purpose:
those rows exist BECAUSE the system holds a black hole, Wolf-Rayet or neutron, so
counting them as observations would be selection on the outcome and would inflate every
rate. Their positives still count in the NUMERATOR for systems that are independently
scanned -- that improves label recall without moving the denominator.

*** Never average a probability across is_catalog without also grouping by mass_code. ***
The catalogued pool is ~89% mass code e (p_bh ~0.04); the boxel-predicted pool has no e
at all and is mostly h (p_bh ~0.46). The gap in mean p_bh is pure composition.

ALREADY-EXPLORED SYSTEMS ARE EXCLUDED, not flagged. Any system holding even one body row
is out of the pool. If a black hole there is already catalogued, somebody has been and
scanned it, so it is not something to predict.

Usage:  python etl/build_system_predicted.py            # DDL + comments only
        python etl/build_system_predicted.py --build    # compute and merge
        python etl/build_system_predicted.py --build --refresh-value
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common.db import (connect, comment_file, apply_comment_file, report_merge,
                       has_primary_key, count_then_update)

TABLE = "system_predicted"
BUILD = "--build" in sys.argv
REFRESH_VALUE = "--refresh-value" in sys.argv

# Same helium fit constants as scripts/build_candidates.py. Changing one here without
# changing it there would silently give the app and the table different answers.
HR_GATE_SGRA = 5500.0
HR_MIN_HE = 29.0
HR_BAND = 0.5
# Boxel key parsed from the procedural name, identical to build_candidates.py. Used only
# to join edastro_boxel_stats, whose key is a NAME string, not our structural columns.
KB = r"regexp_replace({n},'[0-9]+(-[0-9]+)?$','')"
TK = r"regexp_extract({n},'([0-9]+(-[0-9]+)?)$',1)"
BX = ("CASE WHEN " + TK + " LIKE '%-%' THEN " + KB + "||'#'||split_part(" + TK +
      ",'-',1) ELSE " + KB + " END")
# R2's radius bands, so the rates here are directly comparable to the published table.
BAND = ("CASE WHEN plane_r < 10000 THEN '0-10k' WHEN plane_r < 20000 THEN '10-20k' "
        "WHEN plane_r < 30000 THEN '20-30k' ELSE '30k+' END")
# body.code values that define each target. From the `body` dimension, not from names.
BH = "('H','SuperMassiveBlackHole')"
WR = "('W','WN','WNC','WC','WO')"
# Sources that are CATALOGUE-ONLY: they list a body because it is rare, so a system
# known only through them is not evidence of a scan.
CATALOGUE_ONLY = "('edastro_rare','edastro_neutron','canonn_codex')"
DENSITY_MIN = 0.5   # 03s: trust a boxel's internal gaps only if >=50% of min..max is seen
# Wolf-Rayet is fitted only over boxels that are essentially finished -- see the long
# note at the rate fit. WR_FALLBACK is the second tier for cells too thin at the first.
WR_MIN_SCANNED = 10
WR_MIN_FRAC = 0.90
WR_FALLBACK = 0.80

con = connect(memory_limit="16GB", threads=12)
con.execute("CREATE SCHEMA IF NOT EXISTS staging")

# ---------------------------------------------------------------------- DDL ---
# schema/<table>.sql is the master definition -- shape and comments together.
con.execute(comment_file(TABLE).read_text(encoding="utf-8"))
n0 = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
print(f"{TABLE}: {n0:,} existing row(s)")
apply_comment_file(con, comment_file(TABLE))

if not BUILD:
    print("\n  no --build: DDL and comments only.")
    con.close()
    raise SystemExit

# ------------------------------------------------------ per-system labels -----
# Replaces bhwr_system + star_agg. `is_scanned` is deliberately separate from the
# labels: the flag decides the DENOMINATOR, the labels the numerator, and conflating
# them is how a rate fitted on catalogue rows ends up near 1.0.
print("\nlabelling systems from system_body JOIN body...", flush=True)
con.execute(f"""
CREATE OR REPLACE TABLE staging.pred_labels AS
SELECT sb.system_id,
       max(CASE WHEN b.code IN {BH}         THEN 1 ELSE 0 END) AS has_bh,
       max(CASE WHEN b.code IN {WR}         THEN 1 ELSE 0 END) AS has_wr,
       max(CASE WHEN b.code = 'N'           THEN 1 ELSE 0 END) AS has_neutron,
       max(CASE WHEN b.code LIKE 'D%'       THEN 1 ELSE 0 END) AS has_wd,
       max(CASE WHEN b.code = 'AeBe'        THEN 1 ELSE 0 END) AS has_herbig,
       max(CASE WHEN b.code = 'O'           THEN 1 ELSE 0 END) AS has_otype,
       -- '%SuperGiant' ONLY. The wider pattern that also caught K_OrangeGiant and
       -- M_RedGiant returned 324,822 positives against star_agg's 47,866; this one
       -- matches it exactly.
       max(CASE WHEN b.code LIKE '%SuperGiant' THEN 1 ELSE 0 END) AS has_supergiant,
       count(*) FILTER (WHERE b.type = 'star') AS n_stars,
       count(*) FILTER (WHERE sb.source NOT IN {CATALOGUE_ONLY}
                          OR sb.source IS NULL)                 AS n_scan_rows
FROM system_body sb JOIN body b ON b.body_id = sb.body_id
GROUP BY 1""")
r = con.execute("""SELECT count(*), sum(CASE WHEN n_scan_rows > 0 AND n_stars > 0
    THEN 1 ELSE 0 END) FROM staging.pred_labels""").fetchone()
print(f"  {r[0]:,} systems labelled, {r[1]:,} qualify as SCANNED "
      f"({r[0] - r[1]:,} excluded: catalogue-only or no star)")

# --------------------------------------------------- boxel completeness -------
# How much of each boxel has actually been looked at. This is what lets the Wolf-Rayet
# rate be corrected for cherry-picking below, so it is computed before the rates.
print("\nmeasuring boxel scan completeness...", flush=True)
con.execute("""
CREATE OR REPLACE TABLE staging.pred_boxel_scan AS
SELECT k.sector_id, k.cube_id, k.mass_code, k.sub_cube_id,
       count(*) AS known,
       count(*) FILTER (WHERE l.n_scan_rows > 0 AND l.n_stars > 0) AS scanned,
       count(*) FILTER (WHERE l.n_scan_rows > 0 AND l.n_stars > 0)::DOUBLE
         / count(*) AS frac
FROM system_known k LEFT JOIN staging.pred_labels l ON l.system_id = k.system_id
WHERE k.mass_code IN ('e','f','g','h') AND k.cube_id IS NOT NULL
GROUP BY 1,2,3,4""")
for r in con.execute(f"""SELECT mass_code, count(*),
        count(*) FILTER (WHERE scanned >= {WR_MIN_SCANNED} AND frac >= {WR_MIN_FRAC}),
        round(avg(frac), 4)
    FROM staging.pred_boxel_scan GROUP BY 1 ORDER BY 1""").fetchall():
    print(f"    mc={r[0]}  boxels {r[1]:>8,}  fully-explored {r[2]:>7,}  "
          f"mean scanned {r[3]:.1%}")

# ------------------------------------------------- empirical target rates -----
# *** WOLF-RAYET IS FITTED DIFFERENTLY FROM EVERYTHING ELSE, AND THE REASON IS
# MEASURED. *** scripts/refine_rare_rates.py runs the diagnostic; this is its finding.
#
# WR rate in mass code h, against how completely the boxel has been explored:
#
#     10-20% scanned   39.71%        70-80%    34.51%
#     20-30%           45.48%        80-90%    24.76%
#     30-40%           37.83%        90-100%   25.81%
#     50-60%           35.46%
#
# A monotonic decline, and it is the cherry-picking signature: when only a handful of
# systems in a boxel have been visited, those few are disproportionately the ones that
# looked interesting. When everything has been looked at there is no selection left.
# The naive fit over all scanned systems therefore reads ~34% for h/10-20k where the
# fully-explored evidence says ~26% -- about 1.3x too high.
#
# It matters MORE than the bias sounds, because the prediction pool is the RESIDUE of
# the most-explored boxels: h is 89% scanned overall, so an unscanned h system is a
# leftover in a heavily-worked boxel, not a random draw from the galaxy. The
# fully-explored boxels are both the least biased sample AND the closest match to the
# pool's context.
#
# *** THE SAME CORRECTION IS NOT APPLIED TO BLACK HOLES. *** Their curve is not a
# depletion curve: BH in mass code f runs 69.6% -> 31.2% -> 71.1% across the same
# deciles, U-shaped, and fitting on fully-explored boxels RAISES f from 58.6% to 73.2%.
# That is not a bias correction, it is a different population -- which boxels get
# finished is confounded with position, because commanders complete boxels near routes
# and populated space where black holes are common. Correcting BH on that evidence
# would trade a bias we can name for one we cannot. Left naive, deliberately.
print("\nfitting empirical rates by (mass_code, plane_r band)...", flush=True)
con.execute(f"""
CREATE OR REPLACE TABLE staging.pred_rate AS
WITH scanned AS (
  SELECT k.sector_id, k.cube_id, k.sub_cube_id, k.mass_code,
         {BAND.replace('plane_r',
          'sqrt(pow(k.x - 25.21875, 2) + pow(k.z - 25899.96875, 2))')} AS band,
         l.has_bh, l.has_wr, l.has_neutron, l.has_wd, l.has_herbig, l.has_otype,
         l.has_supergiant
  FROM staging.pred_labels l
  JOIN system_known k ON k.system_id = l.system_id
  WHERE k.mass_code IN ('e','f','g','h') AND l.n_scan_rows > 0 AND l.n_stars > 0
),
-- WR only: the same systems, restricted to boxels that are essentially finished.
-- Tiered so a thin cell steps down rather than returning NULL, and the tier is
-- reported, because a rate from 210 systems must not look like one from 78,224.
wr_tier AS (
  SELECT s.mass_code, s.band, s.has_wr,
         CASE WHEN b.scanned >= {WR_MIN_SCANNED} AND b.frac >= {WR_MIN_FRAC}  THEN 1
              WHEN b.scanned >= {WR_MIN_SCANNED} AND b.frac >= {WR_FALLBACK}  THEN 2
              ELSE 3 END AS tier
  FROM scanned s JOIN staging.pred_boxel_scan b
    USING (sector_id, cube_id, mass_code, sub_cube_id)
),
wr_best AS (SELECT mass_code, band, min(tier) AS use_tier FROM wr_tier
            WHERE tier < 3 GROUP BY 1,2),
wr AS (
  SELECT t.mass_code, t.band, coalesce(w.use_tier, 3) AS wr_tier,
         count(*) AS wr_n, avg(t.has_wr) AS r_wr
  FROM wr_tier t LEFT JOIN wr_best w USING (mass_code, band)
  WHERE t.tier = coalesce(w.use_tier, 3)
  GROUP BY 1,2,3
)
SELECT s.mass_code, s.band, count(*) AS n,
       avg(s.has_bh)         AS r_bh,
       wr.r_wr               AS r_wr,
       wr.wr_tier            AS wr_tier,
       wr.wr_n               AS wr_n,
       avg(s.has_neutron)    AS r_neutron,
       avg(s.has_wd)         AS r_wd,
       avg(s.has_herbig)     AS r_herbig,
       avg(s.has_otype)      AS r_otype,
       avg(s.has_supergiant) AS r_supergiant
FROM scanned s LEFT JOIN wr USING (mass_code, band)
GROUP BY 1, 2, wr.r_wr, wr.wr_tier, wr.wr_n""")
WRTIER = {1: f">={int(WR_MIN_FRAC*100)}% boxels", 2: f">={int(WR_FALLBACK*100)}% boxels",
          3: "all scanned"}
print(f"  {'mc':<4}{'band':<9}{'systems':>12}{'BH%':>8}{'WR%':>8}  {'WR basis':<16}"
      f"{'WR n':>10}")
for r in con.execute("""SELECT mass_code, band, n, r_bh, r_wr, wr_tier, wr_n
                        FROM staging.pred_rate ORDER BY mass_code, band""").fetchall():
    print(f"  {r[0]:<4}{r[1]:<9}{r[2]:>12,}{r[3]:>7.2%}{(r[4] or 0):>8.2%}  "
          f"{WRTIER.get(r[5], '-'):<16}{(r[6] or 0):>10,}")

# --------------------------------------------------- helium-rich gas giants ---
# Fitted from FULLY-scanned systems only: a partly-scanned system reporting no helium
# giant may simply not have had its gas giants looked at, and counting it as a negative
# drags every band toward zero. staging.spansh_system is the only source of
# declared-vs-scanned body counts, so it stays -- as RAW input, which is what it is.
print("\nfitting p_hr from published boxel helium...", flush=True)
con.execute(f"""
CREATE OR REPLACE TABLE staging.pred_hr_fit AS
WITH named AS (
  SELECT k.system_id, k.id64, k.mass_code, k.x, k.y, k.z,
         CASE WHEN sc.sector IS NULL OR k.sector_id = 0 THEN k."system"
              ELSE sc.sector || ' ' || k."system" END AS full_name
  FROM system_known k LEFT JOIN sector sc ON sc.sector_id = k.sector_id
  WHERE k.mass_code IN ('e','f','g') AND k.id64 IS NOT NULL
),
scanned AS (
  SELECT bx.helium_avg AS he,
         CASE WHEN EXISTS (SELECT 1 FROM system_body sb JOIN body b ON b.body_id = sb.body_id
                           WHERE sb.system_id = n.system_id
                             AND b.body = 'Helium-rich gas giant') THEN 1 ELSE 0 END AS hr
  FROM named n
  JOIN staging.spansh_system sp ON sp.system_id64 = n.id64
  JOIN staging.edastro_boxel_stats bx ON bx.boxel = {BX.format(n='n.full_name')}
  WHERE sp.declared_body_count > 0
    AND sp.scanned_body_count >= sp.declared_body_count
    AND sqrt(pow(n.x - 25.21875, 2) + pow(n.y + 20.90625, 2)
           + pow(n.z - 25899.96875, 2)) >= {HR_GATE_SGRA}
    AND bx.helium_avg IS NOT NULL AND NOT isnan(bx.helium_avg)
)
SELECT floor(he / {HR_BAND}) * {HR_BAND} AS he_band, count(*) AS n,
       sum(hr) AS k, avg(hr) AS rate
FROM scanned GROUP BY 1 HAVING count(*) >= 200""")
print(f"  {'helium':>8}{'systems':>11}{'hits':>9}{'rate':>9}")
for r in con.execute("""SELECT he_band, n, k, rate FROM staging.pred_hr_fit
                        WHERE rate > 0 OR he_band >= 27 ORDER BY 1""").fetchall():
    print(f"  {r[0]:>8.1f}{r[1]:>11,}{r[2]:>9,}{r[3]:>9.1%}")

# -------------------------------------------------------- expected value ------
# Per MASS CODE only -- R7: value/system varies 25x across mass code but only 0.84-1.15x
# with radius, so banding by radius would add noise. Completeness-corrected below.
have_v = con.execute("""SELECT count(*) FROM duckdb_tables()
    WHERE schema_name='staging' AND table_name='sys_value'""").fetchone()[0]
if have_v and not REFRESH_VALUE:
    print("\nreusing staging.sys_value (pass --refresh-value to recompute)", flush=True)
else:
    print("\ncomputing per-system scan value (570M-row pass)...", flush=True)
    con.execute("""
    CREATE OR REPLACE TABLE staging.sys_value AS
    SELECT sb.system_id, count(*) AS n_bodies, sum(
      CASE WHEN b.value_formula = 'star'
           THEN coalesce(b.cr_value,0)
                + coalesce(sb.solar_masses,0) * coalesce(b.cr_value,0) / 66.25
           ELSE greatest(
                  coalesce(CASE WHEN sb.is_terraformable
                                THEN coalesce(b.cr_value_terraformable, b.cr_value)
                                ELSE b.cr_value END, b.cr_value)
                  * (1 + pow(coalesce(sb.earth_masses,0), 0.2) * 0.56591828), 500)
      END) AS base_cr
    FROM system_body sb JOIN body b ON b.body_id = sb.body_id
    GROUP BY 1""")

comp = con.execute("""
SELECT sum(v.n_bodies)::DOUBLE / nullif(sum(k.body_count), 0)
FROM staging.sys_value v JOIN system_known k USING (system_id)
WHERE k.body_count IS NOT NULL""").fetchone()[0]
print(f"  scan completeness {comp:.3%}  -> full-scan correction x{1/comp:.3f}", flush=True)

con.execute(f"""
CREATE OR REPLACE TABLE staging.pred_value AS
SELECT k.mass_code, count(*) AS n,
       avg(v.n_bodies) AS exp_bodies,
       avg(v.base_cr) / {comp} AS exp_scan_value_cr
FROM staging.sys_value v JOIN system_known k USING (system_id)
WHERE k.mass_code IN ('e','f','g','h') GROUP BY 1""")
print(f"  {'mc':<4}{'systems':>12}{'exp bodies':>13}{'exp Cr (full scan)':>21}")
for r in con.execute("""SELECT mass_code, n, exp_bodies, exp_scan_value_cr
                        FROM staging.pred_value ORDER BY 1""").fetchall():
    print(f"  {r[0]:<4}{r[1]:>12,}{r[2]:>13,.2f}{r[3]:>21,.0f}")

# ------------------------------------------- boxel gaps (was theorised_system) --
# 03s's rule, rebuilt on system_known's STRUCTURAL columns instead of by re-parsing
# names. The bug 03s fixed is preserved here deliberately: Forge boxel numbering does
# not always start at 0 (~28% of h-boxels start higher), so filling 0..max fabricates
# systems that are empty space in game. INTERNAL gaps only, and only where the boxel is
# dense enough that a gap means something.
print("\nenumerating boxel-index gaps from system_known...", flush=True)
con.execute(f"""
CREATE OR REPLACE TABLE staging.pred_boxel_gap AS
WITH bx AS (
  SELECT k.sector_id, k.cube_id, k.mass_code, k.sub_cube_id,
         min(k.boxel_index) AS mn, max(k.boxel_index) AS mx, count(*) AS obs,
         -- ROUNDED AT THE POINT OF COMPUTATION (ETL.md). These centroids are float
         -- avg() over a boxel's members, evaluated in parallel with
         -- preserve_insertion_order=false, so the summation ORDER varies between runs
         -- and float addition is not associative. Left raw they shifted in the last
         -- bits, and plane_r / r_sgra inherited it -- 466 and 500 of 61,239 rows
         -- changing on a re-run that changed nothing. Game coordinates sit on a 1/32 ly
         -- grid, so 5 dp is far finer than anything meaningful.
         round(avg(k.x), 5) AS x, round(avg(k.y), 5) AS y, round(avg(k.z), 5) AS z,
         any_value(sc.sector) AS sector
  FROM system_known k LEFT JOIN sector sc ON sc.sector_id = k.sector_id
  WHERE k.mass_code IN ('f','g','h')
    AND k.boxel_index IS NOT NULL AND k.cube_id IS NOT NULL
  GROUP BY 1,2,3,4
  HAVING max(k.boxel_index) > min(k.boxel_index)
     AND count(*)::DOUBLE / (max(k.boxel_index) - min(k.boxel_index) + 1) >= {DENSITY_MIN}
)
SELECT b.sector_id, b.cube_id, b.mass_code, b.sub_cube_id, b.sector,
       t.gidx AS boxel_index, b.x, b.y, b.z
FROM bx b, unnest(range(b.mn, b.mx + 1)) AS t(gidx)
WHERE NOT EXISTS (SELECT 1 FROM system_known k
                  WHERE k.sector_id = b.sector_id AND k.cube_id = b.cube_id
                    AND k.mass_code = b.mass_code AND k.sub_cube_id = b.sub_cube_id
                    AND k.boxel_index = t.gidx)""")
for r in con.execute("""SELECT mass_code, count(*) FROM staging.pred_boxel_gap
                        GROUP BY 1 ORDER BY 1""").fetchall():
    print(f"    mc={r[0]}: {r[1]:,}")
print(f"    total: "
      f"{con.execute('SELECT count(*) FROM staging.pred_boxel_gap').fetchone()[0]:,}")

# ------------------------------------------------------------ the pool --------
# system_known MINUS system_body, plus the boxel-gap layer. A system holding ANY body
# row is EXPLORED and is not a prediction target -- including bodies contributed by the
# EDAstro full catalogues.
print("\nassembling the candidate pool (system_known MINUS system_body)...", flush=True)
con.execute(f"""
CREATE OR REPLACE TABLE staging.pred_pool AS
WITH known AS (
  SELECT k.system_id, k.id64, k.mass_code, k.x, k.y, k.z, sc.sector AS sector_name,
         CASE WHEN sc.sector IS NULL OR k.sector_id = 0 THEN k."system"
              ELSE sc.sector || ' ' || k."system" END AS system_name
  FROM system_known k
  LEFT JOIN sector sc ON sc.sector_id = k.sector_id
  WHERE k.mass_code IN ('e','f','g','h')
),
unscanned AS (
  SELECT * FROM known u
  WHERE NOT EXISTS (SELECT 1 FROM system_body sb WHERE sb.system_id = u.system_id)
),
gap AS (
  -- The boxel-predicted name is reconstructed from the structural columns, which is
  -- exactly how the procedural name is formed: '<sector> <cube_id> <mass><sub>-<index>'
  -- collapses to '<sector> <cube_id> <mass><index>' when sub_cube_id is 0.
  SELECT CASE WHEN g.sector IS NULL THEN '' ELSE g.sector || ' ' END
         || g.cube_id || ' ' || g.mass_code
         || CASE WHEN g.sub_cube_id = 0 THEN ''
                 ELSE CAST(g.sub_cube_id AS VARCHAR) || '-' END
         || CAST(g.boxel_index AS VARCHAR) AS system_name,
         g.mass_code, g.x, g.y, g.z, g.sector AS sector_name
  FROM staging.pred_boxel_gap g
)
SELECT u.system_name, u.id64 AS system_id64, true AS is_catalog, u.mass_code,
       sqrt(pow(u.x - 25.21875, 2) + pow(u.z - 25899.96875, 2)) AS plane_r,
       u.x, u.y, u.z,
       sqrt(pow(u.x - 25.21875, 2) + pow(u.y + 20.90625, 2)
          + pow(u.z - 25899.96875, 2)) AS r_sgra,
       {BX.format(n='u.system_name')} AS boxel, u.sector_name AS sector
FROM unscanned u
UNION ALL
SELECT g.system_name, NULL, false, g.mass_code,
       sqrt(pow(g.x - 25.21875, 2) + pow(g.z - 25899.96875, 2)),
       g.x, g.y, g.z,
       sqrt(pow(g.x - 25.21875, 2) + pow(g.y + 20.90625, 2)
          + pow(g.z - 25899.96875, 2)),
       {BX.format(n='g.system_name')}, g.sector_name
FROM gap g
-- The CATALOGUED row wins. A gap-derived name that already exists in system_known is
-- not a prediction: the real row has EXACT coordinates while the gap row carries only a
-- boxel centroid, ~300 ly away. Without this the merge aborts on a non-unique natural
-- key, which is what the duplicate guard below is for.
WHERE NOT EXISTS (SELECT 1 FROM known kn WHERE kn.system_name = g.system_name)
""")
for r in con.execute("""SELECT is_catalog, count(*) FROM staging.pred_pool
                        GROUP BY 1 ORDER BY 1 DESC""").fetchall():
    print(f"  {'catalogued_unscanned' if r[0] else 'boxel-predicted':<24}{r[1]:>12,}")
dup = con.execute("""SELECT count(*) FROM (SELECT system_name FROM staging.pred_pool
                     GROUP BY 1 HAVING count(*) > 1)""").fetchone()[0]
if dup:
    sys.exit(f"pool has {dup} duplicate system_name(s) -- refusing to merge on a "
             f"non-unique natural key")

con.execute(f"""
CREATE OR REPLACE TABLE staging.pred_scored AS
SELECT p.system_name, p.system_id64, p.is_catalog, p.mass_code, p.sector, p.boxel,
       p.x, p.y, p.z, round(p.plane_r, 3) AS plane_r, round(p.r_sgra, 3) AS r_sgra,
       round(sqrt(p.x*p.x + p.y*p.y + p.z*p.z), 3) AS dist_sol,
       -- ROUNDED, and not cosmetically. Every p_* is an avg() over millions of rows;
       -- with preserve_insertion_order=false across 12 threads the summation ORDER
       -- varies between runs and float addition is not associative, so the last bits
       -- move. Unrounded, `IS DISTINCT FROM` reports every row as updated on a re-run
       -- that changed nothing, and ETL.md requires a no-op run to LOOK like a no-op.
       round(r.r_bh, 6) AS p_bh, round(r.r_wr, 6) AS p_wr,
       round(CASE WHEN p.mass_code = 'h' THEN 0.0
            WHEN p.r_sgra < {HR_GATE_SGRA} THEN 0.0
            WHEN bx.helium_avg IS NULL OR isnan(bx.helium_avg)
                 OR bx.helium_avg < {HR_MIN_HE} THEN 0.0
            ELSE coalesce(hf.rate, 0.0) END, 6) AS p_hr,
       round(r.r_neutron, 6) AS p_neutron, round(r.r_wd, 6) AS p_wd,
       round(r.r_herbig, 6) AS p_herbig,
       round(r.r_otype, 6) AS p_otype, round(r.r_supergiant, 6) AS p_supergiant,
       round(v.exp_bodies, 3) AS exp_bodies,
       round(v.exp_scan_value_cr, 2) AS exp_scan_value_cr
FROM staging.pred_pool p
LEFT JOIN staging.pred_rate r
  ON r.mass_code = p.mass_code AND r.band = {BAND.replace('plane_r','p.plane_r')}
LEFT JOIN staging.pred_value v ON v.mass_code = p.mass_code
LEFT JOIN staging.edastro_boxel_stats bx ON bx.boxel = p.boxel
LEFT JOIN staging.pred_hr_fit hf
  ON hf.he_band = floor(bx.helium_avg / {HR_BAND}) * {HR_BAND}""")

# ------------------------------------------------------------------ merge -----
COLS = ("system_id64","is_catalog","mass_code","sector","boxel","x","y","z","plane_r",
        "r_sgra","dist_sol","p_bh","p_wr","p_hr","p_neutron","p_wd","p_herbig",
        "p_otype","p_supergiant","exp_bodies","exp_scan_value_cr")
before = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
con.execute(f"""
INSERT INTO {TABLE} (system_predicted_id, system_name, {", ".join(COLS)})
SELECT (SELECT coalesce(max(system_predicted_id), 0) FROM {TABLE})
         + row_number() OVER (ORDER BY s.system_name),
       s.system_name, {", ".join("s." + c for c in COLS)}
FROM staging.pred_scored s
WHERE NOT EXISTS (SELECT 1 FROM {TABLE} k WHERE k.system_name = s.system_name)""")
mid = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]

# IS DISTINCT FROM throughout: `NULL <> 0.5` is NULL, which would skip a backfill and
# leave the column empty forever while still reporting a clean merge.
_CMP = " OR ".join(f"{TABLE}.{c} IS DISTINCT FROM s.{c}" for c in COLS)
_SET = ", ".join(f"{c} = s.{c}" for c in COLS)
_W = f"WHERE {TABLE}.system_name = s.system_name AND ({_CMP})"
upd = count_then_update(con,
    f"SELECT count(*) FROM {TABLE}, staging.pred_scored s {_W}",
    f"UPDATE {TABLE} SET {_SET} FROM staging.pred_scored s {_W}")

# *** THE ONE TABLE THAT DELETES. *** ETL.md's merge-never-drop rule protects surrogate
# keys other tables point at; nothing points at system_predicted, and a PREDICTION that
# has been invalidated is not a retired key, it is a WRONG ROW. A system that has since
# been explored must LEAVE this table or it keeps being offered as a target that no
# longer exists.
orphan = con.execute(f"""SELECT count(*) FROM {TABLE} t
    WHERE NOT EXISTS (SELECT 1 FROM staging.pred_scored s
                      WHERE s.system_name = t.system_name)""").fetchone()[0]
if orphan:
    con.execute(f"""DELETE FROM {TABLE}
        WHERE NOT EXISTS (SELECT 1 FROM staging.pred_scored s
                          WHERE s.system_name = {TABLE}.system_name)""")
    print(f"\n  DELETED {orphan:,} stale prediction(s) -- those systems are no longer "
          f"unexplored (a body of theirs is now known), so they are not predictions any "
          f"more. This table deliberately deletes; see the note in the builder.",
          flush=True)
after = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
report_merge(TABLE, before, after, mid - before, upd, [])
print(f"  {has_primary_key(con, TABLE)}")
apply_comment_file(con, comment_file(TABLE))

# ----------------------------------------------------------------- report -----
print(f"\n  {'is_catalog':<24}{'rows':>12}{'mean p_bh':>11}{'mean p_wr':>11}{'mean p_hr':>11}")
for r in con.execute(f"""SELECT is_catalog, count(*), avg(p_bh), avg(p_wr), avg(p_hr)
                         FROM {TABLE} GROUP BY 1 ORDER BY 1 DESC""").fetchall():
    lab = "TRUE  (catalogued)" if r[0] else "FALSE (boxel-predicted)"
    print(f"  {lab:<24}{r[1]:>12,}{r[2]:>11.4f}{r[3]:>11.4f}{r[4]:>11.4f}")
# These two means are NOT comparable -- different mass-code mixes. Group by mass_code.

print(f"\n  {'mc':<4}{'rows':>12}{'p_bh':>9}{'p_wr':>9}{'p_hr>0':>10}"
      f"{'p_herbig':>10}{'exp Cr':>12}")
for r in con.execute(f"""SELECT mass_code, count(*), avg(p_bh), avg(p_wr),
       count(*) FILTER (WHERE p_hr > 0), avg(p_herbig), avg(exp_scan_value_cr)
       FROM {TABLE} GROUP BY 1 ORDER BY 1""").fetchall():
    print(f"  {r[0]:<4}{r[1]:>12,}{r[2]:>9.4f}{r[3]:>9.4f}{r[4]:>10,}"
          f"{r[5]:>10.4f}{r[6]:>12,.0f}")

nn = con.execute(f"""SELECT count(*) FROM {TABLE}
                     WHERE p_bh IS NULL OR exp_scan_value_cr IS NULL""").fetchone()[0]
print(f"\n  rows missing a rate or value: {nn:,}"
      f"{'  <== CHECK the rate/value joins' if nn else '  (ok)'}")
con.close()
print("\nDONE_BUILD_SYSTEM_PREDICTED")

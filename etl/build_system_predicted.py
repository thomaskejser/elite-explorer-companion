"""Build `system_predicted` -- every system we can predict, with per-target probabilities.

DERIVED table (ETL.md): built from other DB tables, no input/ parquet, no loader.

BUILT ENTIRELY FROM THE MODEL PLUS `staging`, and every input is a table this repo
builds:

  system_known      the system spine. mass_code, x/y/z and the boxel structure are
                    columns there; plane_r / r_sgra / dist_sol are computed here from
                    the Sgr A* constants below.
  system_body JOIN body
                    the labels. has_bh / has_wr / has_neutron / has_wd / has_herbig /
                    has_otype / has_supergiant all come from body.code, so adding a
                    body type to the dimension is what adds a target here.
  staging.pred_boxel_gap
                    the boxel-gap layer, recomputed here from system_known's
                    (sector_id, cube_id, mass_code, sub_cube_id, boxel_index).
                    INTERNAL gaps only, and only in boxels where observed >= 50% of the
                    min..max index range -- filling from 0 would fabricate systems.
                    Yields 216,526: e 154,763, f 14,115, g 15,396, h 32,252. e dominates
                    because it is the largest mass code in system_known by far
                    (4,113,391 rows against f's 476,990).

*** THERE IS NO GRADIENT-BOOSTED SCORE COLUMN, DELIBERATELY. *** A probability this
pipeline cannot recompute could only ever be a permanently-NULL column named like a
probability, which is a trap. Everything here is derived from the tables above, so it
rebuilds from scratch.

`staging.spansh_system` and `staging.edastro_boxel_stats` are NOT read here. They stay
staged because they are RAW SOURCE tables that cost hours to re-download and re-parse,
and declared-vs-scanned body counts and per-boxel aggregates have no substitute
anywhere else in the model.

*** WHAT COUNTS AS SCANNED. *** A system is in the rate DENOMINATOR only if it holds at
least one body row from a real scan (source not in edastro_rare / edastro_neutron /
canonn_codex) and at least one star. Catalogue-only systems are excluded on purpose:
those rows exist BECAUSE the system holds a black hole, Wolf-Rayet or neutron, so
counting them as observations would be selection on the outcome and would inflate every
rate. Their positives still count in the NUMERATOR for systems that are independently
scanned -- that improves label recall without moving the denominator.

*** Never average a probability across is_catalog without also grouping by mass_code. ***
The catalogued pool is ~89% mass code e (p_bh ~0.04) while the boxel-predicted pool is
weighted toward h (p_bh ~0.46), so a mean taken across both measures the mix and not the
odds. This got MORE important, not less, when e joined the boxel layer: e is now the
most numerous mass code in BOTH halves, and it is the one whose rate varies most by
radius band -- 0.0544 inside 10 kly against 0.0020 beyond 30k, a 27x spread that a
single average erases completely.

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

# *** THIS BUILDER PREDICTS STARS ONLY, AND A PLANET CANNOT BE ADDED TO IT. *** A route
# plot reveals the ARRIVAL STAR of each hop and nothing else, so a planet column would
# publish a number no observation this project makes could ever resolve. DEAD_ENDS.md
# records the helium-rich gas giant finding (5.4x enrichment behind a hard radial gate)
# for that reason: real, and not something this pipeline can act on.
#
# Boxel key parsed from the procedural name, filling system_predicted's own `boxel`
# column.
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
DENSITY_MIN = 0.5   # trust a boxel's internal gaps only if >=50% of min..max is seen
# Wolf-Rayet is fitted only over boxels that are essentially finished -- see the long
# note at the rate fit. WR_FALLBACK is the second tier for cells too thin at the first.
WR_MIN_SCANNED = 10
WR_MIN_FRAC = 0.90
WR_FALLBACK = 0.80
# A tier must also yield a WORKABLE SAMPLE, not merely a non-empty one. Falling back
# only on emptiness put h/0-10k on 2,011 systems when the next tier offered tens of
# thousands: the delta added 203,687 newly-known-but-unscanned systems, which diluted
# boxel completeness (h mean 89.0% -> 75.0%) and all but emptied the top tier. A rate
# fitted on a tiny unrepresentative corner is worse than a slightly biased one fitted
# on the bulk.
WR_MIN_SAMPLE = 5000

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
# `is_scanned` is deliberately separate from the
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
       -- SCAN-SOURCED STARS ONLY. Counting catalogue star rows here was a hole in
       -- the very filter this table exists to apply: a system whose only star is a
       -- catalogued neutron -- nobody ever scanned a star there -- passed
       -- `n_scan_rows > 0 AND n_stars > 0` on the strength of its spansh PLANETS and
       -- entered the rate denominator. 53,752 mass-code-h systems, 28% of h. It only
       -- became visible when the neutron catalogue grew 501,527 -> 4,096,733 in a
       -- delta merge and the WR rate moved 5x.
       count(*) FILTER (WHERE b.type = 'star'
                          AND (sb.source NOT IN {CATALOGUE_ONLY}
                            OR sb.source IS NULL))              AS n_stars,
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
# =================================================================================
# THE CROSS. Stellar Forge suppresses large/rare objects in two slabs that straddle the
# x = 0 and z = 0 planes, which on a top-down map of the galaxy read as a giant plus
# sign through Sol. The community traces it to a check meant to keep exotica out of the
# starting bubble that shipped with the wrong bounds; whatever the cause, it is not
# subtle and it is not a sampling artefact.
#
# MEASURED HERE, NOT ASSUMED. Over 2.86M scanned e/f/g/h systems, against what this
# model's own (mass_code, plane_r) rates expect for the same systems:
#
#   least(|x|,|z|)     BH        WR    neutron     WD    O-type  supergiant
#        0-100      0.002x    0.000x   0.000x    0.006x   0.055x    0.000x
#      100-200      0.009x    0.000x   0.000x    0.016x   0.129x    0.002x
#      200-400      0.052x    0.000x   0.038x    0.016x   0.160x    0.021x
#      400-600      0.426x    0.000x   0.400x    0.009x   0.674x    0.358x
#      600-800      0.836x    0.000x   0.572x    0.217x   0.565x    0.413x
#     800-1200      ~1.2x     0.000x   ~1.4x     ~0.7x    ~0.5x     ~0.5x
#       2000+       1.00x     1.00x    1.00x     1.00x    1.00x     1.00x
#
# WOLF-RAYET IS A TRUE ZERO, and it is the widest gate of the lot: 0 observed against
# 354 expected across every system inside 1,200 ly of either plane. Black holes are NOT
# zero -- 7 turned up inside 100 ly where 3,144 were expected -- so this applies a
# measured FACTOR and reserves a hard 0.0 for the targets that actually measure zero.
#
# `cross_d = least(|x|, |z|)`: a system is in the cross when EITHER coordinate is small,
# which is what makes the shape a cross instead of a box.
#
# *** THE BASE RATES ARE FITTED OUTSIDE THE CROSS. *** Fitting them over everything and
# then applying a suppression factor would subtract the effect twice, and would leave the
# "outside" rate biased low by however much of the sample sat in the suppressed slabs.
# So `scanned` below excludes cross_d < CROSS_CLEAR and the factors are measured against
# that clean baseline -- which is why the far bands come out at exactly 1.00x.
CROSS_CLEAR = 2000        # ly from either plane: beyond this, no measurable suppression
CROSS_D = "least(abs(k.x), abs(k.z))"
CROSS_BAND = """CASE WHEN cross_d < 100 THEN '0-100'
                     WHEN cross_d < 200 THEN '100-200'
                     WHEN cross_d < 400 THEN '200-400'
                     WHEN cross_d < 600 THEN '400-600'
                     WHEN cross_d < 800 THEN '600-800'
                     WHEN cross_d < 1000 THEN '800-1000'
                     WHEN cross_d < 1200 THEN '1000-1200'
                     WHEN cross_d < 1400 THEN '1200-1400'
                     WHEN cross_d < 1600 THEN '1400-1600'
                     WHEN cross_d < 2000 THEN '1600-2000'
                     ELSE 'clear' END"""
CROSS_TARGETS = ["bh", "wr", "neutron", "wd", "herbig", "otype", "supergiant"]

print("\nfitting empirical rates by (mass_code, plane_r band), OUTSIDE the cross...",
      flush=True)
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
    -- OUTSIDE THE CROSS ONLY; see the note above. Everything inside is suppressed by a
    -- generator artefact, and averaging it into the baseline would understate the rate
    -- everywhere else while hiding the artefact itself.
    AND {CROSS_D} >= {CROSS_CLEAR}
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
-- pick the STRICTEST tier that still yields WR_MIN_SAMPLE systems; if none does,
-- take whichever tier has the most, so a thin cell degrades rather than lies.
wr_size AS (SELECT mass_code, band, tier, count(*) AS n FROM wr_tier GROUP BY 1,2,3),
wr_big  AS (SELECT mass_code, band, max(n) AS max_n FROM wr_size
            WHERE tier < 3 GROUP BY 1,2),
wr_best AS (
  SELECT s.mass_code, s.band,
         coalesce(min(s.tier) FILTER (WHERE s.n >= {WR_MIN_SAMPLE} AND s.tier < 3),
                  min(s.tier) FILTER (WHERE s.tier < 3 AND s.n = g.max_n),
                  3) AS use_tier
  FROM wr_size s LEFT JOIN wr_big g USING (mass_code, band)
  GROUP BY 1,2),
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
# ---------------------------------------------------------------- the cross -------
# One row per band with a factor per target: observed / expected-under-the-clean-rates.
# A band that observed NOTHING gets a hard 0.0 rather than a small number -- with 354
# Wolf-Rayets expected inside 1,200 ly and none found, "rare here" is the wrong reading
# and "the generator does not put them here" is the right one.
print("\nmeasuring the cross (suppression near the x=0 / z=0 planes)...", flush=True)
_obs_exp = ",\n       ".join(
    f"sum(l.has_{c}::int) AS obs_{c}, sum(r.r_{c}) AS exp_{c}" for c in CROSS_TARGETS)
_factor = ",\n       ".join(
    f"CASE WHEN exp_{c} IS NULL OR exp_{c} = 0 THEN 1.0 "
    f"WHEN obs_{c} = 0 THEN 0.0 ELSE least(round(obs_{c} / exp_{c}, 6), 1.0) END AS f_{c}"
    for c in CROSS_TARGETS)
con.execute(f"""
CREATE OR REPLACE TABLE staging.pred_cross AS
WITH m AS (
  SELECT {CROSS_BAND.replace('cross_d', CROSS_D)} AS cross_band,
         min({CROSS_D}) AS lo, count(*) AS n,
         {_obs_exp}
  FROM staging.pred_labels l
  JOIN system_known k ON k.system_id = l.system_id
  JOIN staging.pred_rate r ON r.mass_code = k.mass_code
       AND r.band = {BAND.replace('plane_r',
        'sqrt(pow(k.x - 25.21875, 2) + pow(k.z - 25899.96875, 2))')}
  WHERE k.mass_code IN ('e','f','g','h') AND l.n_scan_rows > 0 AND l.n_stars > 0
  GROUP BY 1
)
SELECT cross_band, lo, n, {_factor} FROM m""")
# A factor is CAPPED AT 1.0: this table exists to model suppression, and a band coming
# out above 1 means the clean baseline is slightly conservative there, not that the cross
# creates black holes. Letting it inflate would quietly re-fit the rate model by the
# back door.
print(f"  {'band':<12}{'systems':>10}" + "".join(f"{c:>11}" for c in CROSS_TARGETS))
for _r in con.execute("""SELECT cross_band, n, """ +
                      ", ".join(f"f_{c}" for c in CROSS_TARGETS) +
                      " FROM staging.pred_cross ORDER BY lo").fetchall():
    print(f"  {_r[0]:<12}{_r[1]:>10,}" + "".join(f"{v:>10.3f}x" for v in _r[2:]))
con.execute("""COMMENT ON TABLE staging.pred_cross IS
'WORK TABLE, rebuilt by etl/build_system_predicted.py. The Stellar Forge CROSS: how much
the generator suppresses each rare target near the x=0 and z=0 planes, as a factor on the
rate model, keyed by band of least(|x|,|z|). Measured as observed/expected over scanned
e/f/g/h systems against rates fitted OUTSIDE the cross, so the clear band is 1.0 by
construction. A 0.0 means the band observed none at all -- Wolf-Rayet is 0 against 354
expected inside 1,200 ly, which is a generator rule rather than a small number.'""")

WRTIER = {1: f">={int(WR_MIN_FRAC*100)}% boxels", 2: f">={int(WR_FALLBACK*100)}% boxels",
          3: "all scanned"}
print(f"  {'mc':<4}{'band':<9}{'systems':>12}{'BH%':>8}{'WR%':>8}  {'WR basis':<16}"
      f"{'WR n':>10}")
for r in con.execute("""SELECT mass_code, band, n, r_bh, r_wr, wr_tier, wr_n
                        FROM staging.pred_rate ORDER BY mass_code, band""").fetchall():
    print(f"  {r[0]:<4}{r[1]:<9}{r[2]:>12,}{r[3]:>7.2%}{(r[4] or 0):>8.2%}  "
          f"{WRTIER.get(r[5], '-'):<16}{(r[6] or 0):>10,}")

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

# ------------------------------------------------------------- boxel gaps --------
# Built on system_known's STRUCTURAL columns instead of by re-parsing names. The
# INTERNAL-GAPS-ONLY rule is the whole correctness argument here: Forge boxel numbering does
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
         -- and float addition is not associative. Left raw they shift in the last
         -- bits, and plane_r / r_sgra inherit it -- hundreds of rows reported as
         -- changed on a re-run that changed nothing. Game coordinates sit on a 1/32 ly
         -- grid, so 5 dp is far finer than anything meaningful.
         round(avg(k.x), 5) AS x, round(avg(k.y), 5) AS y, round(avg(k.z), 5) AS z,
         any_value(sc.sector) AS sector
  FROM system_known k LEFT JOIN sector sc ON sc.sector_id = k.sector_id
  -- *** e, f, g, h -- THE SAME FOUR EVERY OTHER STAGE OF THIS BUILDER COVERS. *** e is
  -- where black holes START: measured over system_known, primaries run 0 in every one
  -- of the 71.5 MILLION a-d systems that report one, then 77,469 at e -- a 3.9% rate
  -- against 51.5% at f. An e target is a poor bet next to an f one, but it is a real
  -- one, and it accounts for ~78,000 actual black holes.
  --
  -- *** WHAT MAKES IT USEFUL IS THE BAND, NOT THE MASS CODE. *** p_bh at e is fitted
  -- per radius band and spans 27x: 0.0544 inside 10 kly, 0.0236 at 10-20k, 0.0031 at
  -- 20-30k, 0.0020 beyond -- the core band worth flying to, the rim band two orders
  -- below it. Every row is emitted and the display threshold decides, because a
  -- threshold is a viewing choice and this table is the evidence.
  --
  -- e is also 4,113,391 of system_known against f's 476,990, so this is the single
  -- largest thing the layer has ever been asked to enumerate. It stays affordable
  -- because DENSITY_MIN culls first: only boxels that are >=50% observed contribute.
  WHERE k.mass_code IN ('e','f','g','h')
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
         CASE WHEN sc.sector IS NULL OR k.sector_id = 0 THEN k.system_in_sector
              ELSE sc.sector || ' ' || k.system_in_sector END AS system_name
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

CROSS_BAND_POOL = CROSS_BAND.replace("cross_d", "least(abs(p.x), abs(p.z))")
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
       -- EVERY RARE-TARGET PROBABILITY IS MULTIPLIED BY ITS CROSS FACTOR. Inside the
       -- suppressed slabs this is what takes p_wr to a hard 0.0 and p_bh to a few
       -- thousandths of its unsuppressed value; outside, every factor is 1.0 and this
       -- changes nothing. coalesce guards a pool row whose band is somehow absent.
       round(r.r_bh * coalesce(xf.f_bh, 1.0), 6) AS p_bh,
       round(r.r_wr * coalesce(xf.f_wr, 1.0), 6) AS p_wr,
       round(r.r_neutron * coalesce(xf.f_neutron, 1.0), 6) AS p_neutron,
       round(r.r_wd * coalesce(xf.f_wd, 1.0), 6) AS p_wd,
       round(r.r_herbig * coalesce(xf.f_herbig, 1.0), 6) AS p_herbig,
       round(r.r_otype * coalesce(xf.f_otype, 1.0), 6) AS p_otype,
       round(r.r_supergiant * coalesce(xf.f_supergiant, 1.0), 6) AS p_supergiant,
       round(v.exp_bodies, 3) AS exp_bodies,
       round(v.exp_scan_value_cr, 2) AS exp_scan_value_cr
FROM staging.pred_pool p
LEFT JOIN staging.pred_rate r
  ON r.mass_code = p.mass_code AND r.band = {BAND.replace('plane_r','p.plane_r')}
LEFT JOIN staging.pred_cross xf
  ON xf.cross_band = {CROSS_BAND_POOL}
LEFT JOIN staging.pred_value v ON v.mass_code = p.mass_code""")

# ------------------------------------------------------------------ merge -----
COLS = ("system_id64","is_catalog","mass_code","sector","boxel","x","y","z","plane_r",
        "r_sgra","dist_sol","p_bh","p_wr","p_neutron","p_wd","p_herbig",
        "p_otype","p_supergiant","exp_bodies","exp_scan_value_cr")
before = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
con.execute(f"""
INSERT INTO {TABLE} (system_predicted_id, system, {", ".join(COLS)})
SELECT (SELECT coalesce(max(system_predicted_id), 0) FROM {TABLE})
         + row_number() OVER (ORDER BY s.system_name),
       s.system_name, {", ".join("s." + c for c in COLS)}
FROM staging.pred_scored s
WHERE NOT EXISTS (SELECT 1 FROM {TABLE} k WHERE k.system = s.system_name)""")
mid = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]

# IS DISTINCT FROM throughout: `NULL <> 0.5` is NULL, which would skip a backfill and
# leave the column empty forever while still reporting a clean merge.
_CMP = " OR ".join(f"{TABLE}.{c} IS DISTINCT FROM s.{c}" for c in COLS)
_SET = ", ".join(f"{c} = s.{c}" for c in COLS)
_W = f"WHERE {TABLE}.system = s.system_name AND ({_CMP})"
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
                      WHERE s.system_name = t.system)""").fetchone()[0]
if orphan:
    con.execute(f"""DELETE FROM {TABLE}
        WHERE NOT EXISTS (SELECT 1 FROM staging.pred_scored s
                          WHERE s.system_name = {TABLE}.system)""")
    print(f"\n  DELETED {orphan:,} stale prediction(s) -- those systems are no longer "
          f"unexplored (a body of theirs is now known), so they are not predictions any "
          f"more. This table deliberately deletes; see the note in the builder.",
          flush=True)
after = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
report_merge(TABLE, before, after, mid - before, upd, [])
print(f"  {has_primary_key(con, TABLE)}")
apply_comment_file(con, comment_file(TABLE))

# ----------------------------------------------------------------- report -----
print(f"\n  {'is_catalog':<24}{'rows':>12}{'mean p_bh':>11}{'mean p_wr':>11}")
for r in con.execute(f"""SELECT is_catalog, count(*), avg(p_bh), avg(p_wr)
                         FROM {TABLE} GROUP BY 1 ORDER BY 1 DESC""").fetchall():
    lab = "TRUE  (catalogued)" if r[0] else "FALSE (boxel-predicted)"
    print(f"  {lab:<24}{r[1]:>12,}{r[2]:>11.4f}{r[3]:>11.4f}")
# These two means are NOT comparable -- different mass-code mixes. Group by mass_code.

print(f"\n  {'mc':<4}{'rows':>12}{'p_bh':>9}{'p_wr':>9}"
      f"{'p_herbig':>10}{'exp Cr':>12}")
for r in con.execute(f"""SELECT mass_code, count(*), avg(p_bh), avg(p_wr),
       avg(p_herbig), avg(exp_scan_value_cr)
       FROM {TABLE} GROUP BY 1 ORDER BY 1""").fetchall():
    print(f"  {r[0]:<4}{r[1]:>12,}{r[2]:>9.4f}{r[3]:>9.4f}"
          f"{r[4]:>10.4f}{r[5]:>12,.0f}")

nn = con.execute(f"""SELECT count(*) FROM {TABLE}
                     WHERE p_bh IS NULL OR exp_scan_value_cr IS NULL""").fetchone()[0]
print(f"\n  rows missing a rate or value: {nn:,}"
      f"{'  <== CHECK the rate/value joins' if nn else '  (ok)'}")
con.close()
print("\nDONE_BUILD_SYSTEM_PREDICTED")

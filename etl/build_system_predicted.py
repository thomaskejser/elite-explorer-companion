"""Build `system_predicted` -- every system we can predict, with per-target probabilities.

DERIVED table (ETL.md): built from other DB tables, no input/ parquet, no loader.

WHAT IS IN IT. Two populations, kept apart by the `is_catalog` flag because their
reliability is NOT the same:

  is_catalog = TRUE   2,255,468  REAL catalogued systems with EXACT coordinates that
                                 nobody has detail-scanned (bhwr_candidates, 03c).
  is_catalog = FALSE     57,700  BOXEL-PREDICTED: Stellar-Forge-implied systems present
                                 in NO dump -- enumerated internal boxel index gaps
                                 (theorised_system, 03f/03s). BOXEL-CENTROID coordinates
                                 only, and RECOMMENDATIONS.md R2/R3 warns this layer is
                                 thin and heavily core-biased. A lower bound, not a
                                 census.

*** Never average a probability across the two without also grouping by mass_code. ***
The catalogued pool is 89.4% mass code e (p_bh ~0.04); the boxel-predicted pool has NO e
at all and is 51.7% h (p_bh ~0.46). The resulting gap in mean p_bh (0.09 vs 0.43) is pure
composition -- within any single mass code the two agree closely (h: 0.4439 vs 0.4612).

Restricted to mass codes e/f/g/h, which is where every target here is predictable at all:
R1 gates black holes and Wolf-Rayets to e/f/g/h (0.000% below e, confidence A), and
edastro_boxel_stats -- the only helium source -- covers e/f/g/h ONLY, no d and below.

PROBABILITIES. Two families, deliberately in separate columns:

  p_*        EMPIRICAL rates, measured here at build time over SCANNED systems by
             (mass_code, plane_r band), the same cut R1/R2 are stated in. Available for
             BOTH sources. Reproducible in SQL, no model.
  p_*_model  The 03c gradient-boosted ranking, carried from bhwr_candidates. Available
             for catalogued_unscanned ONLY (theorised systems were never scored). Its own
             table comment says RANKINGS are the trustworthy output and absolute values
             are biased upward; app/candidates.parquet holds the flight-calibrated level.

p_hr reproduces build_candidates.py's fit exactly rather than inventing a second one:
two hard gates (r_sgra >= 5500, mass_code <> 'h') plus a fitted lookup on EDAstro's
published per-boxel gas-giant helium fraction. It is NOT normalised against p_bh/p_wr --
a system can hold a black hole and a helium-rich gas giant at once.

exp_scan_value_cr is stratified by MASS CODE only, on purpose: R7 found value per system
varies 25x across mass code but only 0.84-1.15x with distance from Sol, so banding it by
radius would add noise, not signal. It is completeness-corrected (our "scanned" systems
are only 77.1% scanned) so it represents a FULL scan.

ALREADY-FOUND SYSTEMS ARE EXCLUDED, not flagged. Any system holding even one body row
in system_body is out of the pool -- including bodies contributed by the EDAstro FULL
catalogues. If a black hole, Wolf-Rayet or neutron there is already catalogued, somebody
has been and scanned it, so the system is EXPLORED and is not something to predict.
That is why there are no edastro_bh / edastro_wr flag columns: the rows are gone, not
marked.

Usage:  python etl/build_system_predicted.py            # DDL + comments only
        python etl/build_system_predicted.py --build    # compute and merge
        python etl/build_system_predicted.py --build --refresh-value
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common.db import (connect, comment_file, apply_comment_file, report_merge,
                       has_primary_key, count_then_update, assert_shape)

TABLE = "system_predicted"
BUILD = "--build" in sys.argv
REFRESH_VALUE = "--refresh-value" in sys.argv

# Same helium fit constants as scripts/build_candidates.py. Changing one here without
# changing it there would silently give the app and the table different answers.
HR_GATE_SGRA = 5500.0
HR_MIN_HE = 29.0
HR_BAND = 0.5
# Boxel key / index parsed from the procedural name, identical to build_candidates.py.
KB = r"regexp_replace({n},'[0-9]+(-[0-9]+)?$','')"
TK = r"regexp_extract({n},'([0-9]+(-[0-9]+)?)$',1)"
BX = ("CASE WHEN " + TK + " LIKE '%-%' THEN " + KB + "||'#'||split_part(" + TK +
      ",'-',1) ELSE " + KB + " END")
# R2's radius bands, so the rates here are directly comparable to the published table.
BAND = ("CASE WHEN plane_r < 10000 THEN '0-10k' WHEN plane_r < 20000 THEN '10-20k' "
        "WHEN plane_r < 30000 THEN '20-30k' ELSE '30k+' END")

con = connect(memory_limit="14GB", threads=12)
con.execute("CREATE SCHEMA IF NOT EXISTS staging")

# ---------------------------------------------------------------------- DDL ---
# DDL comes from schema/<table>.sql, the ONE definition of this table's shape and
# its comments. The model is created with the database and never altered after,
# so this is CREATE TABLE IF NOT EXISTS -- a no-op on an existing database -- and
# assert_shape() below fails loudly if what is there does not match the file.
con.execute(comment_file(TABLE).read_text(encoding='utf-8'))
assert_shape(con, TABLE)
n0 = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
print(f"{TABLE}: {n0:,} existing row(s)")
apply_comment_file(con, comment_file(TABLE))

if not BUILD:
    print("\n  no --build: DDL and comments only.")
    con.close()
    raise SystemExit

# ------------------------------------------------- empirical target rates -----
# Measured over SCANNED systems only -- the same population R1/R2 are stated over.
# bhwr_system and star_agg are both "scanned systems only" label tables.
print("\nfitting empirical rates by (mass_code, plane_r band) over scanned systems...",
      flush=True)
con.execute(f"""
CREATE OR REPLACE TABLE staging.pred_rate AS
SELECT f.mass_code, {BAND} AS band, count(*) AS n,
       avg(CASE WHEN b.has_bh      THEN 1.0 ELSE 0 END) AS r_bh,
       avg(CASE WHEN b.has_wr      THEN 1.0 ELSE 0 END) AS r_wr,
       avg(CASE WHEN a.has_neutron THEN 1.0 ELSE 0 END) AS r_neutron,
       avg(CASE WHEN a.has_wd      THEN 1.0 ELSE 0 END) AS r_wd,
       avg(CASE WHEN a.has_herbig  THEN 1.0 ELSE 0 END) AS r_herbig,
       avg(CASE WHEN a.has_otype   THEN 1.0 ELSE 0 END) AS r_otype,
       avg(CASE WHEN a.has_supergiant THEN 1.0 ELSE 0 END) AS r_supergiant
FROM sys_feat f
JOIN bhwr_system b ON b.system_id64 = f.system_id64
LEFT JOIN star_agg a ON a.system_id64 = f.system_id64
WHERE f.mass_code IN ('e','f','g','h') AND f.is_scanned AND b.n_stars > 0
GROUP BY 1, 2""")
print(f"  {'mc':<4}{'band':<9}{'systems':>12}{'BH%':>8}{'WR%':>8}{'neutron%':>10}"
      f"{'herbig%':>9}{'O%':>7}{'sgiant%':>9}")
for r in con.execute("""SELECT mass_code, band, n, r_bh, r_wr, r_neutron, r_herbig,
                        r_otype, r_supergiant FROM staging.pred_rate
                        ORDER BY mass_code, band""").fetchall():
    print(f"  {r[0]:<4}{r[1]:<9}{r[2]:>12,}{r[3]:>7.2%}{r[4]:>8.2%}{r[5]:>10.2%}"
          f"{r[6]:>9.2%}{r[7]:>7.2%}{r[8]:>9.2%}")

# --------------------------------------------------- helium-rich gas giants ---
# Reproduces scripts/build_candidates.py exactly: fitted from FULLY-scanned systems only,
# because a partly-scanned system that reports no helium giant may simply not have had its
# gas giants looked at, and counting it as a negative drags every band toward zero.
print("\nfitting p_hr from published boxel helium...", flush=True)
con.execute(f"""
CREATE OR REPLACE TABLE staging.pred_hr_fit AS
WITH scanned AS (
  SELECT bx.helium_avg AS he, coalesce(hb.hr, 0) AS hr
  FROM sys_feat f
  JOIN spansh_system sp ON sp.system_id64 = f.system_id64
  JOIN edastro_boxel_stats bx ON bx.boxel = {BX.format(n='f.name')}
  LEFT JOIN (SELECT system_id64,
                    max(CASE WHEN sub_type='Helium-rich gas giant' THEN 1 ELSE 0 END) hr
             FROM spansh_body GROUP BY 1) hb ON hb.system_id64 = f.system_id64
  WHERE sp.declared_body_count > 0
    AND sp.scanned_body_count >= sp.declared_body_count
    AND f.r_sgra >= {HR_GATE_SGRA} AND f.mass_code <> 'h'
    AND bx.helium_avg IS NOT NULL
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

# Completeness: we hold only ~77% of the bodies of the systems we call scanned, so a
# FULL scan is worth more than our per-system mean suggests. Measured, not assumed.
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

# ------------------------------------------------------------ the pool --------
# DERIVED from system_known MINUS system_body, not taken from bhwr_candidates.
#
# *** A SYSTEM HOLDING ANY BODY ROW IS EXCLUDED. *** That includes rows contributed by
# the EDAstro FULL catalogues (source edastro_rare / edastro_neutron): if a black hole,
# Wolf-Rayet or neutron there is already catalogued, a commander has been and scanned
# it, so the system is EXPLORED and is not a prediction target. This is why the table no
# longer carries edastro_bh / edastro_wr flags -- flagging an already-found system as a
# candidate and relying on the reader to filter is the weaker design, and
# scripts/build_candidates.py already excluded them outright.
#
# Deriving the pool this way also drops the dependency on bhwr_candidates and sys_feat:
# names come from system_known + sector, geometry is computed from x/y/z with the same
# Sgr A* constants as 03a_build_features.py, verified identical. bhwr_candidates is now
# only an optional LEFT JOIN for the model scores, never the source of the pool.
print("\nassembling the candidate pool (system_known MINUS system_body)...", flush=True)
con.execute(f"""
CREATE OR REPLACE TABLE staging.pred_pool AS
WITH known AS (
  SELECT k.system_id, k.mass_code, k.x, k.y, k.z, sc.sector AS sector_name,
         CASE WHEN sc.sector IS NULL THEN k."system"
              ELSE sc.sector || ' ' || k."system" END AS system_name
  FROM system_known k
  LEFT JOIN sector sc ON sc.sector_id = k.sector_id
  WHERE k.mass_code IN ('e','f','g','h')
),
unscanned AS (
  SELECT * FROM known u
  WHERE NOT EXISTS (SELECT 1 FROM system_body sb WHERE sb.system_id = u.system_id)
)
SELECT u.system_name, g.system_id64, true AS is_catalog, u.mass_code,
       sqrt(pow(u.x - 25.21875, 2) + pow(u.z - 25899.96875, 2)) AS plane_r,
       u.x, u.y, u.z,
       sqrt(pow(u.x - 25.21875, 2) + pow(u.y + 20.90625, 2)
          + pow(u.z - 25899.96875, 2)) AS r_sgra,
       {BX.format(n='u.system_name')} AS boxel, u.sector_name AS sector,
       c.p_bh AS p_bh_model, c.p_wr AS p_wr_model
FROM unscanned u
LEFT JOIN staging.sys_bridge g ON g.system_id = u.system_id
LEFT JOIN bhwr_candidates c ON c.name = u.system_name
UNION ALL
SELECT t.boxel_key || CAST(t.boxel_index AS VARCHAR), NULL, false,
       t.mass_code, t.plane_r, t.x, t.y, t.z, t.r_sgra,
       {BX.format(n="t.boxel_key || CAST(t.boxel_index AS VARCHAR)")},
       t.sector, NULL, NULL
FROM theorised_system t
WHERE t.mass_code IN ('e','f','g','h')
  -- The catalogued row WINS. theorised_system claims these are in NO dump, but 1,715 of
  -- them ARE in system_known: 03f built that layer against sys_feat (194.7M), which
  -- lacks the ~2.9M EDAstro-sourced systems that carry no id64 but do exist in
  -- system_known (197.6M). Where both produce a name, the catalogued row has EXACT
  -- coordinates and the theorised one only a boxel centroid ~300 ly away, so the
  -- theorised duplicate is dropped. Without this the merge aborts on a non-unique
  -- natural key -- which is exactly what the duplicate guard below is for.
  AND NOT EXISTS (SELECT 1 FROM known kn
                  WHERE kn.system_name = t.boxel_key || CAST(t.boxel_index AS VARCHAR))
""")
for r in con.execute("""SELECT is_catalog, count(*) FROM staging.pred_pool
                        GROUP BY 1 ORDER BY 1 DESC""").fetchall():
    print(f"  {'catalogued_unscanned' if r[0] else 'boxel-predicted':<24}{r[1]:>12,}")
dup = con.execute("""SELECT count(*) FROM (SELECT system_name FROM staging.pred_pool
                     GROUP BY 1 HAVING count(*) > 1)""").fetchone()[0]
if dup:
    sys.exit(f"pool has {dup} duplicate system_name(s) -- refusing to merge on a "
             f"non-unique natural key")

# EDAstro's full BH/WR catalogues: systems already known to hold one.
con.execute(f"""
CREATE OR REPLACE TABLE staging.pred_scored AS
SELECT p.system_name, p.system_id64, p.is_catalog, p.mass_code, p.sector, p.boxel,
       p.x, p.y, p.z, p.plane_r, p.r_sgra,
       round(sqrt(p.x*p.x + p.y*p.y + p.z*p.z), 3) AS dist_sol,
       -- ROUNDED, and not cosmetically. Every p_* below is an avg() over millions of
       -- rows; with preserve_insertion_order=false across 12 threads the summation
       -- ORDER varies between runs, and float addition is not associative, so the last
       -- bits move. Unrounded, `IS DISTINCT FROM` then reports all 2.3M rows as updated
       -- on a re-run that changed nothing -- and ETL.md requires a no-op run to LOOK
       -- like a no-op. 6 dp is far finer than any of these rates is meaningful to.
       round(r.r_bh, 6) AS p_bh, round(r.r_wr, 6) AS p_wr,
       round(p.p_bh_model, 6) AS p_bh_model, round(p.p_wr_model, 6) AS p_wr_model,
       round(CASE WHEN p.mass_code = 'h' THEN 0.0
            WHEN p.r_sgra < {HR_GATE_SGRA} THEN 0.0
            WHEN bx.helium_avg IS NULL OR bx.helium_avg < {HR_MIN_HE} THEN 0.0
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
LEFT JOIN edastro_boxel_stats bx ON bx.boxel = p.boxel
LEFT JOIN staging.pred_hr_fit hf
  ON hf.he_band = floor(bx.helium_avg / {HR_BAND}) * {HR_BAND}""")

# ------------------------------------------------------------------ merge -----
# ETL.md: match on the NATURAL key (system_name), insert unseen, update matched, never
# renumber a surrogate id, never drop.
before = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
con.execute(f"""
INSERT INTO {TABLE} (system_predicted_id, system_name, system_id64, is_catalog, mass_code,
    sector, boxel, x, y, z, plane_r, r_sgra, dist_sol, p_bh, p_wr, p_bh_model,
    p_wr_model, p_hr, p_neutron, p_wd, p_herbig, p_otype, p_supergiant, exp_bodies,
    exp_scan_value_cr)
SELECT (SELECT coalesce(max(system_predicted_id), 0) FROM {TABLE})
         + row_number() OVER (ORDER BY s.system_name),
       s.system_name, s.system_id64, s.is_catalog, s.mass_code, s.sector, s.boxel,
       s.x, s.y, s.z, s.plane_r, s.r_sgra, s.dist_sol, s.p_bh, s.p_wr, s.p_bh_model,
       s.p_wr_model, s.p_hr, s.p_neutron, s.p_wd, s.p_herbig, s.p_otype,
       s.p_supergiant, s.exp_bodies, s.exp_scan_value_cr
FROM staging.pred_scored s
WHERE NOT EXISTS (SELECT 1 FROM {TABLE} k WHERE k.system_name = s.system_name)""")
mid = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]

# IS DISTINCT FROM throughout: a newly added column is NULL on existing rows and
# `NULL <> 0.5` is NULL, which would skip the backfill and leave it empty forever.
_CMP = " OR ".join(f"{TABLE}.{c} IS DISTINCT FROM s.{c}" for c in
    ("system_id64","is_catalog","mass_code","sector","boxel","x","y","z","plane_r","r_sgra",
     "dist_sol","p_bh","p_wr","p_bh_model","p_wr_model","p_hr","p_neutron","p_wd",
     "p_herbig","p_otype","p_supergiant","exp_bodies","exp_scan_value_cr"))
_SET = ", ".join(f"{c} = s.{c}" for c in
    ("system_id64","is_catalog","mass_code","sector","boxel","x","y","z","plane_r","r_sgra",
     "dist_sol","p_bh","p_wr","p_bh_model","p_wr_model","p_hr","p_neutron","p_wd",
     "p_herbig","p_otype","p_supergiant","exp_bodies","exp_scan_value_cr"))
_W = f"WHERE {TABLE}.system_name = s.system_name AND ({_CMP})"
upd = count_then_update(con,
    f"SELECT count(*) FROM {TABLE}, staging.pred_scored s {_W}",
    f"UPDATE {TABLE} SET {_SET} FROM staging.pred_scored s {_W}")

# *** THE ONE TABLE THAT DELETES. *** ETL.md's merge-never-drop rule protects surrogate
# keys other tables point at; nothing points at system_predicted, and more importantly a
# PREDICTION that has been invalidated is not a retired key, it is a WRONG ROW. A system
# that has since been explored -- or whose black hole now appears in a catalogue -- must
# LEAVE this table, or it keeps being offered as a target that no longer exists. Leaving
# it "in place and reported" would make the table quietly lie.
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
# These two means are NOT comparable -- the pools have different mass-code mixes
# (catalogued is 89.4% e, boxel-predicted has no e at all), so the gap is composition,
# not target quality. Within a mass code the two agree closely. Group by mass_code too.

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

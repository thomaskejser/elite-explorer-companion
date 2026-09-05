import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (apply_comment_file, comment_file, connect, count_then_update,
                       has_primary_key, prepare_table, report_merge, table_count)

TABLE = "system_predicted"
BUILD = "--build" in sys.argv
REFRESH_VALUE = "--refresh-value" in sys.argv

KB = r"regexp_replace({n},'[0-9]+(-[0-9]+)?$','')"
TK = r"regexp_extract({n},'([0-9]+(-[0-9]+)?)$',1)"
BX = ("CASE WHEN " + TK + " LIKE '%-%' THEN " + KB + "||'#'||split_part(" + TK +
      ",'-',1) ELSE " + KB + " END")
BAND = ("CASE WHEN plane_r < 10000 THEN '0-10k' WHEN plane_r < 20000 THEN '10-20k' "
        "WHEN plane_r < 30000 THEN '20-30k' ELSE '30k+' END")
BH = "('H','SuperMassiveBlackHole')"
WR = "('W','WN','WNC','WC','WO')"
CATALOGUE_ONLY = "('edastro_rare','edastro_neutron','canonn_codex')"
DENSITY_MIN = 0.5
WR_MIN_SCANNED = 10
WR_MIN_FRAC = 0.90
WR_FALLBACK = 0.80
WR_MIN_SAMPLE = 5000

con = connect(memory_limit="16GB", threads=12)
con.execute("CREATE SCHEMA IF NOT EXISTS staging")

n0 = prepare_table(con, TABLE, "system_known + system_body")

if not BUILD:
    print("\n  no --build: DDL and comments only.")
    con.close()
    raise SystemExit

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
       max(CASE WHEN b.code LIKE '%SuperGiant' THEN 1 ELSE 0 END) AS has_supergiant,
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

CROSS_CLEAR = 2000
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
    AND {CROSS_D} >= {CROSS_CLEAR}
),
wr_tier AS (
  SELECT s.mass_code, s.band, s.has_wr,
         CASE WHEN b.scanned >= {WR_MIN_SCANNED} AND b.frac >= {WR_MIN_FRAC}  THEN 1
              WHEN b.scanned >= {WR_MIN_SCANNED} AND b.frac >= {WR_FALLBACK}  THEN 2
              ELSE 3 END AS tier
  FROM scanned s JOIN staging.pred_boxel_scan b
    USING (sector_id, cube_id, mass_code, sub_cube_id)
),
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
print(f"  {'band':<12}{'systems':>10}" + "".join(f"{c:>11}" for c in CROSS_TARGETS))
for _r in con.execute("""SELECT cross_band, n, """ +
                      ", ".join(f"f_{c}" for c in CROSS_TARGETS) +
                      " FROM staging.pred_cross ORDER BY lo").fetchall():
    print(f"  {_r[0]:<12}{_r[1]:>10,}" + "".join(f"{v:>10.3f}x" for v in _r[2:]))
con.execute("""COMMENT ON TABLE staging.pred_cross IS
'WORK TABLE, rebuilt by etl/system_predicted/build.py. The Stellar Forge CROSS: how much
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

print("\nenumerating boxel-index gaps from system_known...", flush=True)
con.execute(f"""
CREATE OR REPLACE TABLE staging.pred_boxel_gap AS
WITH bx AS (
  SELECT k.sector_id, k.cube_id, k.mass_code, k.sub_cube_id,
         min(k.boxel_index) AS mn, max(k.boxel_index) AS mx, count(*) AS obs,
         round(avg(k.x), 5) AS x, round(avg(k.y), 5) AS y, round(avg(k.z), 5) AS z,
         any_value(sc.sector) AS sector
  FROM system_known k LEFT JOIN sector sc ON sc.sector_id = k.sector_id
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
      f"{table_count(con, 'staging.pred_boxel_gap'):,}")

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

COLS = ("system_id64","is_catalog","mass_code","sector","boxel","x","y","z","plane_r",
        "r_sgra","dist_sol","p_bh","p_wr","p_neutron","p_wd","p_herbig",
        "p_otype","p_supergiant","exp_bodies","exp_scan_value_cr")
before = table_count(con, TABLE)
con.execute(f"""
INSERT INTO {TABLE} (system_predicted_id, system, {", ".join(COLS)})
SELECT (SELECT coalesce(max(system_predicted_id), 0) FROM {TABLE})
         + row_number() OVER (ORDER BY s.system_name),
       s.system_name, {", ".join("s." + c for c in COLS)}
FROM staging.pred_scored s
WHERE NOT EXISTS (SELECT 1 FROM {TABLE} k WHERE k.system = s.system_name)""")
mid = table_count(con, TABLE)

_CMP = " OR ".join(f"{TABLE}.{c} IS DISTINCT FROM s.{c}" for c in COLS)
_SET = ", ".join(f"{c} = s.{c}" for c in COLS)
_W = f"WHERE {TABLE}.system = s.system_name AND ({_CMP})"
upd = count_then_update(con,
    f"SELECT count(*) FROM {TABLE}, staging.pred_scored s {_W}",
    f"UPDATE {TABLE} SET {_SET} FROM staging.pred_scored s {_W}")

orphan = con.execute(f"""SELECT count(*) FROM {TABLE} t
    WHERE NOT EXISTS (SELECT 1 FROM staging.pred_scored s
                      WHERE s.system_name = t.system)""").fetchone()[0]
if orphan:
    # DELETES, the documented exception in ETL.md 3: an explored system is a WRONG
    # row, not a retired key, and nothing keys into this table.
    con.execute(f"""DELETE FROM {TABLE}
        WHERE NOT EXISTS (SELECT 1 FROM staging.pred_scored s
                          WHERE s.system_name = {TABLE}.system)""")
    print(f"\n  DELETED {orphan:,} stale prediction(s) -- those systems are no longer "
          f"unexplored (a body of theirs is now known), so they are not predictions any "
          f"more. This table deliberately deletes; see the note in the builder.",
          flush=True)
after = table_count(con, TABLE)
report_merge(TABLE, before, after, mid - before, upd, [])
print(f"  {has_primary_key(con, TABLE)}")
apply_comment_file(con, comment_file(TABLE))

print(f"\n  {'is_catalog':<24}{'rows':>12}{'mean p_bh':>11}{'mean p_wr':>11}")
for r in con.execute(f"""SELECT is_catalog, count(*), avg(p_bh), avg(p_wr)
                         FROM {TABLE} GROUP BY 1 ORDER BY 1 DESC""").fetchall():
    lab = "TRUE  (catalogued)" if r[0] else "FALSE (boxel-predicted)"
    print(f"  {lab:<24}{r[1]:>12,}{r[2]:>11.4f}{r[3]:>11.4f}")

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

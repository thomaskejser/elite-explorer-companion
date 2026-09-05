import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (apply_comment_file, comment_file, connect, count_then_update,
                       prepare_table, report_merge, table_count)

TABLE = "system_unfound"
NEAR_LY, MID_LY = 300.0, 1000.0
NEAR_SNR, MIN_SNR = 10.0, 3.0
MATCH_FLOOR, MATCH_SIGMA = 3.0, 3.0   # radius = max(3 ly, 3 x dist/snr)
ANCHOR_LY = 20.0

con = connect()
print(f"database: {con.execute('SELECT current_database()').fetchone()[0]}")
before = prepare_table(con, TABLE, "system_catalog + staging.catalog_parallax")

if not con.execute("""SELECT count(*) FROM duckdb_tables()
                      WHERE schema_name='staging'
                        AND table_name='catalog_parallax'""").fetchone()[0]:
    sys.exit("staging.catalog_parallax is missing -- it carries the astrometry this table\n"
             "is built from. Seed it before running this.")

con.execute(f"""CREATE OR REPLACE TEMP TABLE cand AS
SELECT c.system, c.type, p.plx, p.eplx, p.plx / p.eplx AS snr, p.glon, p.glat,
       3.26156 * 1000 / p.plx AS dist_ly,
       -3.26156 * 1000 / p.plx * cos(radians(p.glat)) * sin(radians(p.glon)) AS x,
        3.26156 * 1000 / p.plx * sin(radians(p.glat))                        AS y,
        3.26156 * 1000 / p.plx * cos(radians(p.glat)) * cos(radians(p.glon)) AS z,
       p.vmag, p.sp_type
FROM system_catalog c
JOIN staging.catalog_parallax p ON p.system = c.system
WHERE c.system_id IS NULL
  AND p.usable AND p.plx > 0 AND p.eplx > 0 AND p.glon IS NOT NULL
  AND p.plx / p.eplx >= {MIN_SNR}
  AND 3.26156 * 1000 / p.plx < {MID_LY}
QUALIFY row_number() OVER (PARTITION BY c.system ORDER BY p.plx / p.eplx DESC) = 1""")
n_cand = table_count(con, 'cand')
print(f"  {n_cand:,} unresolved catalogue star(s) with a usable position inside "
      f"{MID_LY:,.0f} ly")

con.execute("""CREATE OR REPLACE TEMP TABLE hn AS
SELECT system_in_sector AS s, x, y, z FROM system_known WHERE sector_id = 0""")
con.execute(f"""CREATE OR REPLACE TEMP TABLE nearest AS
SELECT c.system,
       min_by(h.s, sqrt(pow(c.x-h.x,2) + pow(c.y-h.y,2) + pow(c.z-h.z,2))) AS nearest,
       min(sqrt(pow(c.x-h.x,2) + pow(c.y-h.y,2) + pow(c.z-h.z,2)))         AS nearest_ly
FROM cand c JOIN hn h
  ON abs(c.x-h.x) < {ANCHOR_LY} AND abs(c.y-h.y) < {ANCHOR_LY}
 AND abs(c.z-h.z) < {ANCHOR_LY}
GROUP BY 1""")
con.execute("""CREATE OR REPLACE TEMP TABLE sec AS
SELECT c.system,
       min_by(s.sector_id, pow(c.x-s.x,2) + pow(c.y-s.y,2) + pow(c.z-s.z,2)) AS sector_id,
       min_by(s.sector,    pow(c.x-s.x,2) + pow(c.y-s.y,2) + pow(c.z-s.z,2)) AS sector
FROM cand c CROSS JOIN sector s
WHERE s.sector_id <> 0
GROUP BY 1""")

con.execute(f"""CREATE OR REPLACE TEMP TABLE final AS
SELECT c.system, c.type, round(c.x,4) AS x, round(c.y,4) AS y, round(c.z,4) AS z,
       round(c.dist_ly,2) AS dist_ly, round(c.snr,2) AS plx_snr, c.vmag, c.sp_type,
       CASE WHEN c.dist_ly < {NEAR_LY} AND c.snr >= {NEAR_SNR} THEN 'near' ELSE 'mid' END
         AS band,
       sc.sector_id, sc.sector, n.nearest, round(n.nearest_ly,3) AS nearest_ly
FROM cand c LEFT JOIN nearest n USING (system) LEFT JOIN sec sc USING (system)
WHERE n.nearest_ly IS NULL
   OR n.nearest_ly >= greatest({MATCH_FLOOR}, {MATCH_SIGMA} * c.dist_ly / c.snr)""")
for r in con.execute("""SELECT band, type, count(*) FROM final
                        GROUP BY 1,2 ORDER BY 1, 3 DESC""").fetchall():
    print(f"    {r[0]:<6}{r[1]:<5}{r[2]:>8,}")

con.execute(f"""INSERT INTO {TABLE}
    (system, type, x, y, z, dist_ly, plx_snr, vmag, sp_type, band, sector_id, sector,
     nearest, nearest_ly)
    SELECT f.system, f.type, f.x, f.y, f.z, f.dist_ly, f.plx_snr, f.vmag, f.sp_type,
           f.band, f.sector_id, f.sector, f.nearest, f.nearest_ly
    FROM final f
    WHERE NOT EXISTS (SELECT 1 FROM {TABLE} t WHERE t.system = f.system)""")
mid = table_count(con, TABLE)
upd = count_then_update(
    con,
    f"""SELECT count(*) FROM {TABLE} t JOIN final f USING (system)
        WHERE t.band IS DISTINCT FROM f.band OR t.nearest IS DISTINCT FROM f.nearest
           OR t.nearest_ly IS DISTINCT FROM f.nearest_ly
           OR t.dist_ly IS DISTINCT FROM f.dist_ly""",
    f"""UPDATE {TABLE} AS t SET x = f.x, y = f.y, z = f.z, dist_ly = f.dist_ly,
            plx_snr = f.plx_snr, vmag = f.vmag, sp_type = f.sp_type, band = f.band,
            sector_id = f.sector_id, sector = f.sector,
            nearest = f.nearest, nearest_ly = f.nearest_ly
        FROM final AS f WHERE f.system = t.system
          AND (t.band IS DISTINCT FROM f.band OR t.nearest IS DISTINCT FROM f.nearest
               OR t.nearest_ly IS DISTINCT FROM f.nearest_ly
               OR t.dist_ly IS DISTINCT FROM f.dist_ly)""")

# DELETES, which ETL.md 3 allows only for a table that predicts rather than records.
# A row here claims a star cannot be found; an alias resolving it, or somebody visiting
# it, makes the claim false rather than the key retired. Nothing keys into this table.
gone = con.execute(f"""SELECT count(*) FROM {TABLE} t
    WHERE NOT EXISTS (SELECT 1 FROM final f WHERE f.system = t.system)""").fetchone()[0]
if gone:
    con.execute(f"""DELETE FROM {TABLE}
        WHERE NOT EXISTS (SELECT 1 FROM final f WHERE f.system = {TABLE}.system)""")
    print(f"  DELETED {gone:,} row(s) that are no longer unfound -- resolved by a new "
          f"alias, or now in a dump.")
after = table_count(con, TABLE)
report_merge(TABLE, before, after, mid - before, upd, [])
apply_comment_file(con, comment_file(TABLE))

print("\n  the strongest candidates -- 'near', with something to fly to:")
print(f"    {'system':<14}{'ly':>8}{'snr':>7}{'Vmag':>7}{'type':<10}{'nearest':<24}{'hop':>7}")
for r in con.execute(f"""SELECT system, dist_ly, plx_snr, vmag, coalesce(sp_type,''),
        coalesce(nearest,'--'), nearest_ly FROM {TABLE}
        WHERE band = 'near' ORDER BY coalesce(nearest_ly, 1e9), dist_ly LIMIT 12""").fetchall():
    print(f"    {r[0]:<14}{r[1]:>8.1f}{r[2]:>7.1f}{(r[3] or 0):>7.2f} {r[4][:9]:<9}"
          f"{r[5][:23]:<24}{(r[6] if r[6] is not None else float('nan')):>7.2f}")
con.close()
print("\nDONE_BUILD_SYSTEM_UNFOUND")

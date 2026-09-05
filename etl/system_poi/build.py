import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (apply_comment_file, comment_file, connect, count_then_update,
                       prepare_table, report_merge, table_count)

TABLE = "system_poi"
COLUMNS = ["system_id", "poi_id", "system", "sector", "x", "y", "z"]
KEY = ["system_id", "poi_id"]

con = connect()
before = prepare_table(con, TABLE, "system_known + system_body")

# COMPOSES THE NAME BY CONCATENATING SECTOR, which ETL.md 3 otherwise forbids: this
# table exists to hand the overlay a pasteable name. Only sector_id = 0 stands alone;
# 581 POI systems were wrong when the same thing was done at query time.
NAME = ("CASE WHEN k.sector_id = 0 THEN k.system_in_sector "
        "ELSE sc.sector || ' ' || k.system_in_sector END")

con.execute(f"""
CREATE OR REPLACE TEMP TABLE src AS
SELECT k.system_id, k.id_poi AS poi_id, {NAME} AS system, sc.sector, k.x, k.y, k.z
FROM system_known k
JOIN sector sc ON sc.sector_id = k.sector_id
WHERE k.id_poi IS NOT NULL
UNION
SELECT k.system_id, sb.id_poi, {NAME}, sc.sector, k.x, k.y, k.z
FROM system_body sb
JOIN system_known k ON k.system_id = sb.system_id
JOIN sector sc      ON sc.sector_id = k.sector_id
WHERE sb.id_poi IS NOT NULL""")

n_src, n_sys, n_sysknown, n_body = con.execute("""
    SELECT (SELECT count(*) FROM src),
           (SELECT count(DISTINCT system_id) FROM src),
           (SELECT count(*) FROM system_known WHERE id_poi IS NOT NULL),
           (SELECT count(*) FROM system_body  WHERE id_poi IS NOT NULL)""").fetchone()
print(f"  {n_src:,} (system, POI) pair(s) over {n_sys:,} system(s)")
print(f"  from {n_sysknown:,} system-level and {n_body:,} body-level attribution(s)")

ON = " AND ".join(f"s.{c} = t.{c}" for c in KEY)
CHANGED = " OR ".join(f't."{c}" IS DISTINCT FROM s."{c}"'
                      for c in COLUMNS if c not in KEY)
SETS = ", ".join(f'"{c}" = s."{c}"' for c in COLUMNS if c not in KEY)
cols = ", ".join(f'"{c}"' for c in COLUMNS)

updated = count_then_update(
    con,
    f"SELECT count(*) FROM {TABLE} t JOIN src s ON {ON} WHERE {CHANGED}",
    f"UPDATE {TABLE} AS t SET {SETS} FROM src AS s WHERE {ON} AND ({CHANGED})")

con.execute(f"""
    INSERT INTO {TABLE} ({cols})
    SELECT {cols} FROM src s
    WHERE NOT EXISTS (SELECT 1 FROM {TABLE} t WHERE {ON})""")

after = table_count(con, TABLE)
orphans = [f"{r[0]}/{r[1]}" for r in con.execute(f"""
    SELECT system_id, poi_id FROM {TABLE} t
    WHERE NOT EXISTS (SELECT 1 FROM src s WHERE {ON}) LIMIT 5""").fetchall()]
report_merge(TABLE, before, after, after - before, updated, orphans)

apply_comment_file(con, comment_file(TABLE))

print(f"\n  {'POI':<34}{'systems':>10}")
for r in con.execute(f"""
    SELECT p.poi, count(*) FROM {TABLE} sp JOIN poi p USING (poi_id)
    GROUP BY 1 ORDER BY 2 DESC LIMIT 10""").fetchall():
    print(f"  {r[0][:33]:<34}{r[1]:>10,}")

missing = con.execute(f"SELECT count(*) FROM {TABLE} WHERE x IS NULL").fetchone()[0]
print(f"\n  without coordinates: {missing:,} -- cannot be ranked by distance")

print("\nDONE_BUILD_SYSTEM_POI")

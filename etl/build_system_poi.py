"""BUILD system_poi: which systems hold a point of interest, both attributions in one
table.

    python etl/build_system_poi.py

SOURCE: system_known.id_poi and system_body.id_poi -- the answers the model already
holds -- plus poi and sector. NOT common.poi_link, which resolves RAW observations into
those two columns: re-deriving from staging here would be a second opinion that could
disagree with the model the overlay reads. This reads the stored answer, so it cannot.

WHY MATERIALISE. The union of the two attributions IS the question "does this system
hold a POI", and the overlay asks it on every repaint. Asked live, the body half has
nothing to probe on and scans system_body's 577,639,044 rows to reach 10,023 -- almost
all of the Current sector table's time, since the prediction CTE alone is 23 ms against
797 ms warm and 2,141 cold for the whole query. Here the probe is 1.6 ms.

Merge; never drop. All the work is SQL; Python only drives it.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common.db import (apply_comment_file, comment_file, connect,
                       count_then_update, report_merge)

TABLE = "system_poi"
# ONE list, walked by the SELECT, the UPDATE and the INSERT, so the three cannot drift.
COLUMNS = ["system_id", "poi_id", "system", "sector", "x", "y", "z"]
KEY = ["system_id", "poi_id"]

con = connect()
con.execute(comment_file(TABLE).read_text(encoding="utf-8"))
before = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
print(f"{TABLE}: {before:,} row(s) before; source system_known + system_body")

# *** sector_id = 0 IS THE 'crafted' SENTINEL AND ITS NAME STANDS ALONE. *** 581 POI
# systems were hit by this when it was done at query time. Composed once, here.
NAME = ("CASE WHEN k.sector_id = 0 THEN k.system_in_sector "
        "ELSE sc.sector || ' ' || k.system_in_sector END")

# UNION, not UNION ALL: a system attributed at both levels for the same POI is ONE
# fact, not two, and the primary key would refuse the second row anyway.
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

# UPDATE before INSERT, or the rows just inserted get scanned again.
updated = count_then_update(
    con,
    f"SELECT count(*) FROM {TABLE} t JOIN src s ON {ON} WHERE {CHANGED}",
    f"UPDATE {TABLE} AS t SET {SETS} FROM src AS s WHERE {ON} AND ({CHANGED})")

con.execute(f"""
    INSERT INTO {TABLE} ({cols})
    SELECT {cols} FROM src s
    WHERE NOT EXISTS (SELECT 1 FROM {TABLE} t WHERE {ON})""")

after = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
# A pair the sources no longer produce. NEVER deleted: a retraction upstream is far more
# often a re-attribution to another body in the SAME system than "it was never there".
# Reported, so if this stops being small you go and find out which source changed.
orphans = [f"{r[0]}/{r[1]}" for r in con.execute(f"""
    SELECT system_id, poi_id FROM {TABLE} t
    WHERE NOT EXISTS (SELECT 1 FROM src s WHERE {ON}) LIMIT 5""").fetchall()]
report_merge(TABLE, before, after, after - before, updated, orphans)

apply_comment_file(con, comment_file(TABLE))

# ---- the shape of what we just built ----------------------------------------------
print(f"\n  {'POI':<34}{'systems':>10}")
for r in con.execute(f"""
    SELECT p.poi, count(*) FROM {TABLE} sp JOIN poi p USING (poi_id)
    GROUP BY 1 ORDER BY 2 DESC LIMIT 10""").fetchall():
    print(f"  {r[0][:33]:<34}{r[1]:>10,}")

missing = con.execute(f"SELECT count(*) FROM {TABLE} WHERE x IS NULL").fetchone()[0]
print(f"\n  without coordinates: {missing:,} -- cannot be ranked by distance")

print("\nDONE_BUILD_SYSTEM_POI")

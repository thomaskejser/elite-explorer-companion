import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (apply_comment_file, comment_file, connect, count_then_update,
                       prepare_table, report_merge, table_count)

TABLE = "carrier_position"
COLUMNS = ["callsign", "system", "x", "y", "z"]
KEY = "callsign"

con = connect()
before = prepare_table(con, TABLE, "carrier + system_known")

# COMPOSES THE NAME BY CONCATENATING SECTOR, which ETL.md 3 otherwise forbids: the
# pasteable name is the point of this table and sys_bridge does not carry one. Only
# sector_id = 0 stands alone, and 2,044 of the 2,524 reliable carriers sit in
# hand-named systems, so the sentinel is the common case here, not the edge.
con.execute(f"""
CREATE OR REPLACE TEMP TABLE src AS
SELECT c.callsign,
       CASE WHEN k.sector_id = 0 THEN k.system_in_sector
            ELSE sc.sector || ' ' || k.system_in_sector END AS system,
       k.x, k.y, k.z
FROM carrier c
JOIN system_known k ON k.system_id = c.system_id
JOIN sector sc      ON sc.sector_id = k.sector_id""")

n_src, n_carrier, n_reliable, n_located = con.execute("""
    SELECT (SELECT count(*) FROM src),
           (SELECT count(*) FROM carrier),
           (SELECT count(*) FROM carrier WHERE is_reliable),
           (SELECT count(*) FROM src WHERE x IS NOT NULL)""").fetchone()
print(f"  {n_src:,} of {n_carrier:,} carrier(s) resolve to a system "
      f"({n_located:,} with coordinates)")
print(f"  {n_reliable:,} are RELIABLE, which is the only pool the overlay offers")

CHANGED = " OR ".join(f't."{c}" IS DISTINCT FROM s."{c}"' for c in COLUMNS if c != KEY)
SETS = ", ".join(f'"{c}" = s."{c}"' for c in COLUMNS if c != KEY)
cols = ", ".join(f'"{c}"' for c in COLUMNS)

updated = count_then_update(
    con,
    f"SELECT count(*) FROM {TABLE} t JOIN src s USING ({KEY}) WHERE {CHANGED}",
    f"""UPDATE {TABLE} AS t SET {SETS}
        FROM src AS s WHERE s.{KEY} = t.{KEY} AND ({CHANGED})""")

con.execute(f"""
    INSERT INTO {TABLE} ({cols})
    SELECT {cols} FROM src s
    WHERE NOT EXISTS (SELECT 1 FROM {TABLE} t WHERE t.{KEY} = s.{KEY})""")

after = table_count(con, TABLE)
orphans = [r[0] for r in con.execute(f"""
    SELECT {KEY} FROM {TABLE} t
    WHERE NOT EXISTS (SELECT 1 FROM src s WHERE s.{KEY} = t.{KEY}) LIMIT 5""").fetchall()]
report_merge(TABLE, before, after, after - before, updated, orphans)

apply_comment_file(con, comment_file(TABLE))

missing = con.execute(f"""
    SELECT count(*) FROM {TABLE} p JOIN carrier c USING (callsign)
    WHERE c.is_reliable AND p.x IS NULL""").fetchone()[0]
print(f"\n  reliable carriers with no coordinates: {missing:,} -- these cannot be "
      f"ranked by distance and never appear in a 'nearest' list")

print("\nDONE_BUILD_CARRIER_POSITION")

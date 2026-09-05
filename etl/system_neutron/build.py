import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (apply_comment_file, comment_file, connect, count_then_update,
                       prepare_table, report_merge, table_count)

TABLE = "system_neutron"
COLUMNS = ["system_id", "sector_id", "system_in_sector", "cube_id", "mass_code", "sub_cube_id",
           "boxel_index", "region_id", "primary_star_body_id", "body_count",
           "x", "y", "z", "id_poi", "id64"]
KEY = "system_id"

con = connect()
before = prepare_table(con, TABLE, "system_known")

neutron = con.execute(
    "SELECT body_id FROM body WHERE type = 'star' AND body = 'Neutron Star'").fetchone()
if not neutron:
    raise SystemExit("body has no 'Neutron Star' row -- run etl/body/build.py first")
neutron_id = neutron[0]
print(f"  'Neutron Star' is body_id {neutron_id}")

cols = ", ".join(f'"{c}"' for c in COLUMNS)
con.execute(f"""
CREATE OR REPLACE TEMP TABLE src AS
SELECT {cols} FROM system_known WHERE primary_star_body_id = ?""", [neutron_id])

n_src, n_known, n_primary = con.execute(f"""
    SELECT (SELECT count(*) FROM src),
           (SELECT count(*) FROM system_known),
           (SELECT count(primary_star_body_id) FROM system_known)""").fetchone()
print(f"  {n_src:,} system(s) with a neutron primary")
print(f"  A FLOOR, NOT A CENSUS: system_known records a primary for only "
      f"{n_primary:,} of {n_known:,} rows ({n_primary / n_known:.1%}), so a system "
      f"absent here may just be one nobody has reported a primary for")

CHANGED = " OR ".join(f't."{c}" IS DISTINCT FROM s."{c}"' for c in COLUMNS if c != KEY)
SETS = ", ".join(f'"{c}" = s."{c}"' for c in COLUMNS if c != KEY)
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

print(f"\n  {'mass code':<14}{'systems':>12}")
for r in con.execute(f"""
    SELECT coalesce(mass_code, '(hand-named)'), count(*) FROM {TABLE}
    GROUP BY 1 ORDER BY 1""").fetchall():
    print(f"  {r[0]:<14}{r[1]:>12,}")

missing = con.execute(f"SELECT count(*) FROM {TABLE} WHERE x IS NULL").fetchone()[0]
print(f"\n  without coordinates: {missing:,} -- cannot be ranked by distance")

print("\nDONE_BUILD_SYSTEM_NEUTRON")

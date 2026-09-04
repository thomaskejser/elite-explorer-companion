"""BUILD carrier_position: where each fleet carrier is, resolved once.

    python etl/build_carrier_position.py

SOURCE: carrier + system_known + sector. No staging, no feed -- every value already
exists in the model and this only resolves it.

WHY MATERIALISE. "Which reliable carriers are nearest" is asked on every jump, and
resolving 2,524 carriers through system_known's 200,676,922 rows has nothing to probe
on, so DuckDB scans the lot: 1,440 ms warm, 5,224 cold. Here it is 1.8 ms. Same
precedent as system_neutron.

*** RE-RUN AFTER EVERY carrier LOAD *** -- a carrier that jumped keeps its old position
here until you do.

Merge; never drop. All the work is SQL; Python only drives it.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common.db import (apply_comment_file, comment_file, connect,
                       count_then_update, report_merge)

TABLE = "carrier_position"
# ONE list, walked by the SELECT, the UPDATE and the INSERT, so the three cannot drift.
COLUMNS = ["callsign", "system", "x", "y", "z"]
KEY = "callsign"

con = connect()
con.execute(comment_file(TABLE).read_text(encoding="utf-8"))
before = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
print(f"{TABLE}: {before:,} row(s) before; source carrier + system_known")

# *** sector_id = 0 IS THE 'crafted' SENTINEL AND ITS NAME STANDS ALONE. *** 2,044 of
# the 2,524 reliable carriers sit in hand-named systems, so getting this wrong made most
# nearest-carrier names uncopyable -- and it produced a plausible string every time.
# Composed here so the mistake can only be made once.
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

# UPDATE before INSERT, or the rows just inserted get scanned again. IS DISTINCT FROM so
# a value becoming NULL still counts as a change.
updated = count_then_update(
    con,
    f"SELECT count(*) FROM {TABLE} t JOIN src s USING ({KEY}) WHERE {CHANGED}",
    f"""UPDATE {TABLE} AS t SET {SETS}
        FROM src AS s WHERE s.{KEY} = t.{KEY} AND ({CHANGED})""")

con.execute(f"""
    INSERT INTO {TABLE} ({cols})
    SELECT {cols} FROM src s
    WHERE NOT EXISTS (SELECT 1 FROM {TABLE} t WHERE t.{KEY} = s.{KEY})""")

after = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
# A callsign carrier no longer resolves. NEVER deleted -- the last known position is
# still the last known position. Reported so a growing number is visible.
orphans = [r[0] for r in con.execute(f"""
    SELECT {KEY} FROM {TABLE} t
    WHERE NOT EXISTS (SELECT 1 FROM src s WHERE s.{KEY} = t.{KEY}) LIMIT 5""").fetchall()]
report_merge(TABLE, before, after, after - before, updated, orphans)

apply_comment_file(con, comment_file(TABLE))

# ---- the shape of what we just built ----------------------------------------------
missing = con.execute(f"""
    SELECT count(*) FROM {TABLE} p JOIN carrier c USING (callsign)
    WHERE c.is_reliable AND p.x IS NULL""").fetchone()[0]
print(f"\n  reliable carriers with no coordinates: {missing:,} -- these cannot be "
      f"ranked by distance and never appear in a 'nearest' list")

print("\nDONE_BUILD_CARRIER_POSITION")

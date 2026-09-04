"""LOAD system_seen from the unmigrated JSON stores. Merge; never drop.

SOURCE: input/unmigrated/starclass.json (name -> arrival star class) and
input/unmigrated/starpos.json (name -> [x,y,z]). Two files, ONE grain -- both are keyed
by system name and both are written by the same act of plotting a route -- so they
become one table here.

A one-way migration: the overlay writes system_seen directly. This is a MERGE, so
re-running it inserts anything the stores still hold that the table does not and leaves
everything else untouched.

*** WRITES ONLY TO elite_mapping_v2_current.duckdb. *** The model database is attached
READ_ONLY, purely to resolve id64. See common/current.py for why that boundary exists.

Parsing is done by DuckDB rather than Python -- read_text + ::MAP(VARCHAR,...) turns a
name-keyed JSON object into rows directly -- so the merge, the outer join between the
two stores and the id64 resolution are all one SQL statement each.

    python etl/load_system_seen.py
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common.current import STORES, begin, finish

TABLE = "system_seen"
CLASS_JSON = STORES / "starclass.json"
POS_JSON = STORES / "starpos.json"

con, before = begin(TABLE)

# FULL OUTER JOIN, not a left join from either side: a system can have a class with no
# position (revealed by FSDTarget) and -- though none exists today -- a position with no
# class. Anchoring on either file alone would silently drop the other's exclusives.
con.execute(f"""
CREATE OR REPLACE TEMP TABLE src AS
WITH cls AS (
  SELECT unnest(map_keys(m)) AS system, unnest(map_values(m)) AS star_class
  FROM (SELECT (content::JSON)::MAP(VARCHAR, VARCHAR) AS m
        FROM read_text('{CLASS_JSON.as_posix()}'))
), pos AS (
  SELECT unnest(map_keys(m)) AS system, unnest(map_values(m)) AS xyz
  FROM (SELECT (content::JSON)::MAP(VARCHAR, DOUBLE[]) AS m
        FROM read_text('{POS_JSON.as_posix()}'))
)
SELECT coalesce(c.system, p.system) AS system,
       c.star_class,
       p.xyz[1] AS x, p.xyz[2] AS y, p.xyz[3] AS z
FROM cls c FULL OUTER JOIN pos p USING (system)""")

n_src, n_cls, n_pos = con.execute(
    "SELECT count(*), count(star_class), count(x) FROM src").fetchone()
print(f"  staged {n_src:,} name(s): {n_cls:,} with a class, {n_pos:,} with a position")

# UPDATE first, then INSERT: the reverse would update the rows just inserted.
# IS DISTINCT FROM so NULL-to-value and value-to-NULL both count, and an unchanged row
# is not rewritten. coalesce on the target side means a store that has FORGOTTEN a fact
# cannot erase one we already hold -- the JSON files are rebuilt from journals that get
# deleted, so a shrinking source is normal and must never delete knowledge.
updated = con.execute(f"""
    SELECT count(*) FROM {TABLE} t JOIN src s USING (system)
    WHERE t.star_class IS DISTINCT FROM coalesce(s.star_class, t.star_class)
       OR t.x          IS DISTINCT FROM coalesce(s.x, t.x)
       OR t.y          IS DISTINCT FROM coalesce(s.y, t.y)
       OR t.z          IS DISTINCT FROM coalesce(s.z, t.z)""").fetchone()[0]
if updated:
    con.execute(f"""
        UPDATE {TABLE} AS t
        SET star_class = coalesce(s.star_class, t.star_class),
            x = coalesce(s.x, t.x), y = coalesce(s.y, t.y), z = coalesce(s.z, t.z)
        FROM src AS s WHERE s.system = t.system""")

con.execute(f"""
    INSERT INTO {TABLE} (system, star_class, x, y, z, id64, first_seen_utc)
    SELECT s.system, s.star_class, s.x, s.y, s.z, NULL, NULL
    FROM src s WHERE NOT EXISTS
      (SELECT 1 FROM {TABLE} t WHERE t.system = s.system)""")

after = finish(con, TABLE, before, updated)
print("  (a system with no id64 is one no catalogue has reported -- expected, and "
      "exactly why it was worth flying to)")

print(f"\n  {'star class':<14}{'systems':>9}   (top 12; H/W* are the finds)")
for cls, n in con.execute(f"""SELECT star_class, count(*) FROM {TABLE}
        GROUP BY 1 ORDER BY 2 DESC LIMIT 12""").fetchall():
    tag = "  <== BLACK HOLE" if cls == "H" else (
          "  <== WOLF-RAYET" if cls and cls.startswith("W") else "")
    print(f"  {str(cls):<14}{n:>9,}{tag}")

print("\nDONE_LOAD_SYSTEM_SEEN")

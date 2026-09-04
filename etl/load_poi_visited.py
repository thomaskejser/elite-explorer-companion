"""LOAD poi_visited from the unmigrated JSON stores. Merge; never drop.

SOURCE: input/unmigrated/poi_seen.json -- a bare JSON array of system names -- plus
input/unmigrated/nsp_seen.json, whose contents it subsumes. Both are read so the
migration does not depend on that continuing to hold.

The stores record only THAT you had been to a system, never WHAT was in it, so the POI
kind is recovered by asking the model -- and the model resolves very few of them,
because a system it has never heard of has no id_poi. That is expected; see the
poi_visited.poi_id comment. Rows the overlay writes carry the kind directly.

*** WRITES ONLY TO elite_mapping_v2_current.duckdb. *** The model is attached READ_ONLY
purely to look up the POI kind. See common/current.py.

    python etl/load_poi_visited.py
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common.current import STORES, attach_model, begin, finish

TABLE = "poi_visited"
PATHS = [STORES / "poi_seen.json", STORES / "nsp_seen.json"]

con, before = begin(TABLE)

present = [p for p in PATHS if p.exists()]
if not present:
    raise SystemExit(f"no POI store found -- looked for {[str(p) for p in PATHS]}")
union = "\nUNION\n".join(
    f"SELECT unnest((content::JSON)::VARCHAR[]) AS system "
    f"FROM read_text('{p.as_posix()}')" for p in present)
con.execute(f"CREATE OR REPLACE TEMP TABLE src AS SELECT DISTINCT system FROM ({union})")
print(f"  staged {con.execute('SELECT count(*) FROM src').fetchone()[0]:,} system(s) "
      f"from {', '.join(p.name for p in present)}")

# Resolve the POI kind where the model knows it. SYSTEM-level id_poi first, then
# BODY-level: a POI pinned to a named body is attributed to the body and not the
# system, so looking only at system_known would miss those. min() picks one
# deterministically for the handful of systems holding more than one kind -- only 8
# systems in the whole galaxy hold more than one poi_class, so the loss is negligible
# and a stable choice beats an arbitrary one.
alias = attach_model(con)
if alias:
    con.execute(f"""
    CREATE OR REPLACE TEMP TABLE kind AS
    WITH ids AS (
      SELECT s.system, b.system_id64, b.system_id
      FROM src s JOIN {alias}.staging.sys_bridge b ON b.sys_name = s.system
    ), best AS (
      SELECT i.system, i.system_id64,
             min(coalesce(k.id_poi, sb.id_poi)) AS poi_id
      FROM ids i
      LEFT JOIN {alias}.main.system_known k ON k.system_id = i.system_id
      LEFT JOIN {alias}.main.system_body sb
             ON sb.system_id = i.system_id AND sb.id_poi IS NOT NULL
      GROUP BY 1, 2
    )
    SELECT b.system, b.system_id64, b.poi_id, p.poi, p.poi_class
    FROM best b LEFT JOIN {alias}.main.poi p ON p.poi_id = b.poi_id""")
else:
    con.execute("""CREATE OR REPLACE TEMP TABLE kind AS
        SELECT NULL::VARCHAR system, NULL::BIGINT system_id64,
               NULL::INTEGER poi_id, NULL::VARCHAR poi, NULL::VARCHAR poi_class
        WHERE FALSE""")
    print("  model database unavailable -- POI kinds left NULL (not an error)")

# Fill in a kind we did not have before. Never overwrite one with NULL: the model
# losing track of a POI must not erase what we recorded at the time.
updated = con.execute(f"""
    SELECT count(*) FROM {TABLE} t JOIN kind k USING (system)
    WHERE t.poi_id IS NULL AND k.poi_id IS NOT NULL""").fetchone()[0]
if updated:
    con.execute(f"""
        UPDATE {TABLE} AS t
        SET poi_id = k.poi_id, poi = k.poi, poi_class = k.poi_class
        FROM kind AS k
        WHERE k.system = t.system
          AND t.poi_id IS NULL AND k.poi_id IS NOT NULL""")

con.execute(f"""
    INSERT INTO {TABLE} (system, id64, poi_id, poi, poi_class, visited_utc)
    SELECT s.system, k.system_id64, k.poi_id, k.poi, k.poi_class, NULL
    FROM src s LEFT JOIN kind k USING (system)
    WHERE NOT EXISTS (SELECT 1 FROM {TABLE} t WHERE t.system = s.system)""")

after = finish(con, TABLE, before, updated)

resolved = con.execute(f"SELECT count(poi_id) FROM {TABLE}").fetchone()[0]
print(f"  poi kind: {resolved:,}/{after:,} resolved ({resolved/after:.1%}) -- the rest "
      f"are systems the model has no id_poi for, which is expected for a migrated row")
for r in con.execute(f"""SELECT coalesce(poi_class, '(unresolved)'), count(*)
        FROM {TABLE} GROUP BY 1 ORDER BY 2 DESC""").fetchall():
    print(f"    {r[0]:<16}{r[1]:>6,}")

print("\nDONE_LOAD_POI_VISITED")

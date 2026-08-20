"""MERGE input/poi.parquet into the `poi` table. Never drops, never renumbers.

input/poi.parquet is AUTHORITATIVE for the POI dimension and is safe to hand-edit --
which is the point, because deciding whether EDAstro's `nebula` and `Nebulae` are one
POI or two is a judgement call no script can make. This loader reconciles additively:

  * CREATE TABLE IF NOT EXISTS -- never OR REPLACE, so the PRIMARY KEY and the two
    foreign keys pointing at poi_id (system_known.id_poi, system_body.id_poi) survive
    a reload. CREATE OR REPLACE would silently drop both, without warning.
  * matched on the NATURAL key `poi`, never on poi_id. New kinds take the parquet's
    poi_id when it is free, otherwise max+1.
  * existing rows keep their poi_id forever. Renumbering would silently repoint every
    id_poi in a 197M-row and a 570M-row table.
  * rows in the table but absent from the parquet are LEFT ALONE and reported; their
    ids are retired, never reused.

`systems` and `bodies` are DERIVED statistics, not dimension attributes: they are
recomputed here from system_known/system_body on every run, and the parquet's copies
are an ignored snapshot. That is why a merge can report updates when you have not
touched the file -- the same contract as body.observed / body.bodies.

Usage:  python etl/load_poi.py
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common.db import (count_then_update, INPUT, connect,
                       has_primary_key, comment_file, apply_comment_file)

TABLE = "poi"
SRC = INPUT / "poi.parquet"
if not SRC.exists():
    sys.exit(f"missing authoritative source {SRC}\n"
             f"seed it first with: python etl/build_poi.py")

con = connect(memory_limit="8GB")

# DDL comes from schema/<table>.sql, the ONE definition of this table's shape and
# its comments. The model is created with the database and never altered after,
# so this is CREATE TABLE IF NOT EXISTS -- a no-op on an existing database.
con.execute(comment_file(TABLE).read_text(encoding='utf-8'))

before = con.execute("SELECT count(*) FROM poi").fetchone()[0]
con.execute(f"CREATE OR REPLACE TEMP TABLE src AS SELECT * FROM '{SRC.as_posix()}'")
n_src = con.execute("SELECT count(*) FROM src").fetchone()[0]
print(f"table poi: {before} existing row(s);  source {SRC.name}: {n_src} row(s)")

dup = con.execute("SELECT poi, count(*) FROM src GROUP BY 1 HAVING count(*) > 1").fetchall()
if dup:
    sys.exit(f"source has duplicate natural keys, refusing to merge: {dup[:10]}")

# --- allocate ids for genuinely new natural keys ------------------------------
con.execute("""
CREATE OR REPLACE TEMP TABLE newrows AS
WITH missing AS (
  SELECT s.* FROM src s WHERE NOT EXISTS (SELECT 1 FROM poi p WHERE p.poi = s.poi)
),
tagged AS (
  SELECT m.*, (m.poi_id IS NOT NULL
               AND NOT EXISTS (SELECT 1 FROM poi p WHERE p.poi_id = m.poi_id)) AS keep_id
  FROM missing m
)
SELECT CASE WHEN keep_id THEN poi_id
            ELSE (SELECT coalesce(max(poi_id), 0) FROM poi)
                 + row_number() OVER (ORDER BY poi_id, poi) END AS poi_id,
       poi, poi_class, poi_family, needs_landing, sources, keep_id
FROM tagged
""")
# row_number() runs over ALL new rows, so ids stay unique when some keep theirs; close
# the gaps that creates. Same trick as load_body.py.
con.execute("""UPDATE newrows SET poi_id = poi_id -
    (SELECT count(*) FROM newrows n2 WHERE n2.keep_id AND n2.poi_id < newrows.poi_id)
WHERE NOT keep_id""")

ins = con.execute("""
INSERT INTO poi (poi_id, poi, poi_class, poi_family, needs_landing, sources,
                 systems, bodies)
SELECT poi_id, poi, poi_class, poi_family, needs_landing, sources, NULL, NULL
FROM newrows RETURNING poi_id""").fetchall()

# --- update dimension attributes of matched rows (never poi_id) ---------------
_W = """WHERE poi.poi = s.poi
  AND (poi.poi_class     IS DISTINCT FROM s.poi_class
    OR poi.poi_family    IS DISTINCT FROM s.poi_family
    OR poi.needs_landing IS DISTINCT FROM s.needs_landing
    OR poi.sources       IS DISTINCT FROM s.sources)"""
upd = count_then_update(con,
    f"SELECT count(*) FROM poi, src s {_W}",
    f"""UPDATE poi SET poi_class = s.poi_class, poi_family = s.poi_family,
        needs_landing = s.needs_landing, sources = s.sources FROM src s {_W}""")

# --- recompute the derived statistics -----------------------------------------
# Guarded: id_poi arrives with build_system_known.py --poi / build_system_body.py --poi,
# so on a database where those have not run yet the columns do not exist and the counts
# stay NULL rather than crashing the dimension load.
have = lambda t, c: con.execute("""SELECT count(*) FROM duckdb_columns()
    WHERE table_name = ? AND column_name = ?""", [t, c]).fetchone()[0] > 0
sk, sb = have("system_known", "id_poi"), have("system_body", "id_poi")
if sk or sb:
    con.execute(f"""CREATE OR REPLACE TABLE staging.poi_counts AS
        SELECT p.poi_id,
               {'(SELECT count(*) FROM system_known k WHERE k.id_poi = p.poi_id)'
                if sk else 'CAST(NULL AS BIGINT)'}::INTEGER AS systems,
               {'(SELECT count(*) FROM system_body b WHERE b.id_poi = p.poi_id)'
                if sb else 'CAST(NULL AS BIGINT)'}::INTEGER AS bodies
        FROM poi p""")
    _WS = """WHERE poi.poi_id = c.poi_id
      AND (poi.systems IS DISTINCT FROM c.systems OR poi.bodies IS DISTINCT FROM c.bodies)"""
    stats = count_then_update(con,
        f"SELECT count(*) FROM poi, staging.poi_counts c {_WS}",
        f"UPDATE poi SET systems = c.systems, bodies = c.bodies FROM staging.poi_counts c {_WS}")
else:
    stats = 0
    print("  NOTE: neither system_known.id_poi nor system_body.id_poi exists yet --\n"
          "        systems/bodies left NULL. Run the --poi phases, then reload.")

orphan = con.execute("""SELECT poi_id, poi FROM poi p
    WHERE NOT EXISTS (SELECT 1 FROM src s WHERE s.poi = p.poi) ORDER BY poi_id""").fetchall()
after = con.execute("SELECT count(*) FROM poi").fetchone()[0]
print(f"\nmerged: {len(ins)} inserted, {upd} attribute update(s), "
      f"{stats} statistic update(s), {before} -> {after} rows")
if orphan:
    print(f"  {len(orphan)} row(s) in the table but NOT in the source -- left in place,\n"
          f"  ids RETIRED (never reuse), deletion is a manual decision:")
    for r in orphan[:20]:
        print(f"    poi_id={r[0]:<5} {r[1]}")

con.execute("CREATE SCHEMA IF NOT EXISTS staging")
apply_comment_file(con, comment_file(TABLE))
pk = con.execute("""SELECT constraint_text FROM duckdb_constraints()
        WHERE table_name='poi' AND constraint_type='PRIMARY KEY'""").fetchone()
print(f"  {pk[0] if pk else 'NO PRIMARY KEY'}")

print(f"\n  {'class':<10}{'kinds':>7}{'landing':>9}{'systems':>12}{'bodies':>12}")
for r in con.execute("""SELECT poi_class, count(*), count(*) FILTER (WHERE needs_landing),
        sum(systems), sum(bodies) FROM poi GROUP BY 1 ORDER BY 1""").fetchall():
    f = lambda v: "-" if v is None else f"{v:,}"
    print(f"  {r[0]:<10}{r[1]:>7}{r[2]:>9}{f(r[3]):>12}{f(r[4]):>12}")
con.close()
print("\nDONE_LOAD_POI")

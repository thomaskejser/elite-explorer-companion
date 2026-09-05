import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (INPUT, apply_comment_file, comment_file, connect,
                       count_then_update, prepare_table, table_count)

TABLE = "poi"
SRC = INPUT / "poi.parquet"
if not SRC.exists():
    sys.exit(f"missing authoritative source {SRC}\n"
             f"seed it first with: python etl/poi/build.py")

con = connect(memory_limit="8GB")

before = prepare_table(con, TABLE, SRC.name)
con.execute(f"CREATE OR REPLACE TEMP TABLE src AS SELECT * FROM '{SRC.as_posix()}'")
n_src = table_count(con, 'src')
print(f"  source {SRC.name}: {n_src} row(s)")

dup = con.execute("SELECT poi, count(*) FROM src GROUP BY 1 HAVING count(*) > 1").fetchall()
if dup:
    sys.exit(f"source has duplicate natural keys, refusing to merge: {dup[:10]}")

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
con.execute("""UPDATE newrows SET poi_id = poi_id -
    (SELECT count(*) FROM newrows n2 WHERE n2.keep_id AND n2.poi_id < newrows.poi_id)
WHERE NOT keep_id""")

ins = con.execute("""
INSERT INTO poi (poi_id, poi, poi_class, poi_family, needs_landing, sources,
                 systems, bodies)
SELECT poi_id, poi, poi_class, poi_family, needs_landing, sources, NULL, NULL
FROM newrows RETURNING poi_id""").fetchall()

_W = """WHERE poi.poi = s.poi
  AND (poi.poi_class     IS DISTINCT FROM s.poi_class
    OR poi.poi_family    IS DISTINCT FROM s.poi_family
    OR poi.needs_landing IS DISTINCT FROM s.needs_landing
    OR poi.sources       IS DISTINCT FROM s.sources)"""
upd = count_then_update(con,
    f"SELECT count(*) FROM poi, src s {_W}",
    f"""UPDATE poi SET poi_class = s.poi_class, poi_family = s.poi_family,
        needs_landing = s.needs_landing, sources = s.sources FROM src s {_W}""")

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
after = table_count(con, 'poi')
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

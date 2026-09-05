import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (INPUT, apply_comment_file, comment_file, connect,
                       count_then_update, has_primary_key, prepare_table,
                       report_merge, table_count)

SRC = INPUT / "region.parquet"
TABLE = "region"

if not SRC.exists():
    sys.exit(f"missing authoritative source {SRC}\n"
             f"seed it once with: python etl/region/build.py")

con = connect()

before = prepare_table(con, TABLE, SRC.name)

con.execute(f"CREATE OR REPLACE TEMP TABLE src AS SELECT * FROM '{SRC.as_posix()}'")
n_src = table_count(con, 'src')
print(f"source {SRC.name}: {n_src} row(s)")

bad = con.execute("""SELECT count(*) FROM src
    WHERE region_id IS NULL OR region IS NULL OR trim(region) = ''""").fetchone()[0]
if bad:
    sys.exit(f"source has {bad} row(s) with a null/blank region_id or region -- "
             f"refusing to merge")
for col in ("region_id", "region"):
    dup = con.execute(f"""SELECT {col}, count(*) FROM src
                          GROUP BY 1 HAVING count(*) > 1""").fetchall()
    if dup:
        sys.exit(f"source has duplicate {col}: {dup} -- refusing to merge "
                 f"(both columns are unique keys)")

# region_id is the GAME's id, not a surrogate of ours: taken from the file as given
# rather than allocated max+1 (ETL.md 3).
ins = con.execute(f"""
INSERT INTO {TABLE} (region_id, region)
SELECT s.region_id, s.region FROM src s
WHERE NOT EXISTS (SELECT 1 FROM {TABLE} t WHERE t.region_id = s.region_id)
RETURNING region_id, region""").fetchall()
for rid, nm in ins:
    print(f"  INSERT region_id={rid:<4} {nm}")

_W = f"""WHERE {TABLE}.region_id = s.region_id
  AND {TABLE}.region IS DISTINCT FROM s.region"""
upd = count_then_update(con,
    f"SELECT count(*) FROM {TABLE}, src s {_W}",
    f"UPDATE {TABLE} SET region = s.region FROM src s {_W}")

orphan = con.execute(f"""SELECT region_id, region FROM {TABLE} t
    WHERE NOT EXISTS (SELECT 1 FROM src s WHERE s.region_id = t.region_id)
    ORDER BY region_id""").fetchall()

after = table_count(con, TABLE)
report_merge(TABLE, before, after, len(ins), upd, orphan)

apply_comment_file(con, comment_file(TABLE))

pk = has_primary_key(con, TABLE)
print(f"  {pk or 'NO PRIMARY KEY'}")
ncc = con.execute("""SELECT count(*) FILTER (WHERE comment IS NOT NULL), count(*)
     FROM duckdb_columns() WHERE schema_name = 'main' AND table_name = ?""",
     [TABLE]).fetchone()
print(f"  column comments: {ncc[0]}/{ncc[1]}"
      + ("" if ncc[0] == ncc[1] else "   <== INCOMPLETE, see ETL.md"))

print(f"\n  {'id':>4}  region")
for r in con.execute(f"SELECT region_id, region FROM {TABLE} ORDER BY region_id").fetchall():
    print(f"  {r[0]:>4}  {r[1]}")
con.close()
print("\nDONE_LOAD_REGION")

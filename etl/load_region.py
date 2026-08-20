"""MERGE input/region.parquet into the `region` table. Never drops, never renumbers.

input/region.parquet is AUTHORITATIVE and HAND-MAINTAINED -- unlike every other table
here, `region` has no upstream feed to re-derive from. Frontier's 42 galactic regions
are hand-drawn and not computable from names or coordinates, so the file IS the source.

Reconciliation is additive (ETL.md):
  * CREATE TABLE IF NOT EXISTS -- never OR REPLACE, so the PRIMARY KEY and any foreign
    key pointing at region_id survive a reload.
  * region_id is the GAME'S OWN id, so unlike body_id it is NOT ours to allocate: it
    comes from the file and is taken as given. A row with a new id is inserted with
    that id; we never renumber and never invent one.
  * matched rows have their name updated (a localisation fix or a Frontier rename).
  * rows here but absent from the file are LEFT ALONE and reported -- app/regions.parquet
    keys 545,485 labelled points on these ids, so a deletion is a manual decision.

Usage:  python etl/load_region.py
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common.db import (count_then_update, ROOT, INPUT, connect, has_primary_key, report_merge,
                       comment_file, apply_comment_file)

SRC = INPUT / "region.parquet"
TABLE = "region"

if not SRC.exists():
    sys.exit(f"missing authoritative source {SRC}\n"
             f"seed it once with: python etl/build_region.py")

con = connect()

# DDL comes from schema/<table>.sql, the ONE definition of this table's shape and
# its comments. The model is created with the database and never altered after,
# so this is CREATE TABLE IF NOT EXISTS -- a no-op on an existing database.
con.execute(comment_file(TABLE).read_text(encoding='utf-8'))
before = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
print(f"table {TABLE}: {before} existing row(s)")

con.execute(f"CREATE OR REPLACE TEMP TABLE src AS SELECT * FROM '{SRC.as_posix()}'")
n_src = con.execute("SELECT count(*) FROM src").fetchone()[0]
print(f"source {SRC.name}: {n_src} row(s)")

# The file is hand-maintained, so validate it rather than trusting it.
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

ins = con.execute(f"""
INSERT INTO {TABLE} (region_id, region)
SELECT s.region_id, s.region FROM src s
WHERE NOT EXISTS (SELECT 1 FROM {TABLE} t WHERE t.region_id = s.region_id)
RETURNING region_id, region""").fetchall()
for rid, nm in ins:
    print(f"  INSERT region_id={rid:<4} {nm}")

# No RETURNING: region is FK-referenced by system_known, and DuckDB blocks
# UPDATE ... RETURNING on referenced rows (see common.db.count_then_update).
_W = f"""WHERE {TABLE}.region_id = s.region_id
  AND {TABLE}.region IS DISTINCT FROM s.region"""
upd = count_then_update(con,
    f"SELECT count(*) FROM {TABLE}, src s {_W}",
    f"UPDATE {TABLE} SET region = s.region FROM src s {_W}")

orphan = con.execute(f"""SELECT region_id, region FROM {TABLE} t
    WHERE NOT EXISTS (SELECT 1 FROM src s WHERE s.region_id = t.region_id)
    ORDER BY region_id""").fetchall()

after = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
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

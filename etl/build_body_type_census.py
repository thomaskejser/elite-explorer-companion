"""Build `body_type_census` -- how many bodies of each type/sub_type exist.

DERIVED table: computed from spansh_body, so there is no input/ file and no
load_body_type_census.py. See ETL.md for the build-vs-load convention.

Merge semantics per ETL.md: the table is created IF NOT EXISTS and upserted on its
natural key (type, sub_type). It is never dropped, so anything that comes to
reference it survives a refresh. Counts change on every Spansh refresh, so matched
rows ARE updated -- that is the point of the table.

This is the denominator for "how rare is X". It counts DISCOVERED bodies, not
bodies in the galaxy, and NOT mapped bodies -- no source carries a DSS flag. Our
body data covers only 38.6% of spine systems, and holds ~77% of the bodies the game
declares even within those, so nothing here is a galaxy total.

Usage:  python etl/build_body_type_census.py
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common.db import count_then_update, ROOT, connect, report_merge, comment_file, apply_comment_file

HERE = pathlib.Path(__file__).resolve().parent

TABLE = "body_type_census"

con = connect()

# DDL comes from schema/<table>.sql, the ONE definition of this table's shape and
# its comments. The model is created with the database and never altered after,
# so this is CREATE TABLE IF NOT EXISTS -- a no-op on an existing database.
con.execute(comment_file(TABLE).read_text(encoding='utf-8'))
before = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
print(f"{TABLE}: {before} existing row(s)")

print("counting bodies by type/sub_type...", flush=True)
con.execute("""
CREATE OR REPLACE TEMP TABLE fresh AS
WITH t AS (
  SELECT type, coalesce(sub_type, '(unspecified)') AS sub_type, count(*) AS bodies
  FROM spansh_body GROUP BY 1, 2
)
SELECT type, sub_type, bodies,
       round(100.0 * bodies / sum(bodies) OVER (),                  6) AS share_all_pct,
       round(100.0 * bodies / sum(bodies) OVER (PARTITION BY type), 6) AS share_of_type_pct
FROM t
""")

# IS DISTINCT FROM, not <>: NULL <> x is NULL, which would silently skip backfilling
# any column added by a later additive migration.
# No RETURNING -- DuckDB blocks it once a row is FK-referenced (see count_then_update).
_W = f"""WHERE {TABLE}.type = f.type AND {TABLE}.sub_type = f.sub_type
  AND ({TABLE}.bodies IS DISTINCT FROM f.bodies
       OR {TABLE}.share_all_pct IS DISTINCT FROM f.share_all_pct
       OR {TABLE}.share_of_type_pct IS DISTINCT FROM f.share_of_type_pct)"""
upd = count_then_update(con,
    f"SELECT count(*) FROM {TABLE}, fresh f {_W}",
    f"""UPDATE {TABLE} SET bodies = f.bodies, share_all_pct = f.share_all_pct,
        share_of_type_pct = f.share_of_type_pct FROM fresh f {_W}""")

ins = con.execute(f"""
INSERT INTO {TABLE}
SELECT f.* FROM fresh f
WHERE NOT EXISTS (SELECT 1 FROM {TABLE} t
                  WHERE t.type = f.type AND t.sub_type = f.sub_type)
RETURNING type, sub_type""").fetchall()
for t, s in ins:
    print(f"  INSERT {t}/{s}")

orphan = con.execute(f"""SELECT type, sub_type FROM {TABLE} t
    WHERE NOT EXISTS (SELECT 1 FROM fresh f
                      WHERE f.type=t.type AND f.sub_type=t.sub_type)""").fetchall()

after = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
report_merge(TABLE, before, after, len(ins), upd, orphan)

# Comment text (table + every column) lives beside this script per ETL.md, and is
# re-asserted after every merge because a schema change silently drops comments.
apply_comment_file(con, comment_file(TABLE))

# schema_name='main' matters: duckdb_columns() also lists the norm.* views.
ncc = con.execute("""SELECT count(*) FILTER (WHERE comment IS NOT NULL), count(*)
     FROM duckdb_columns() WHERE schema_name = 'main' AND table_name = ?""",
     [TABLE]).fetchone()
print(f"  column comments: {ncc[0]}/{ncc[1]}"
      + ("" if ncc[0] == ncc[1] else "   <== INCOMPLETE, see ETL.md"))

print(f"\n  {'type':<7}{'sub_type':<40}{'bodies':>14}{'of type%':>10}")
for r in con.execute(f"""SELECT type, sub_type, bodies, share_of_type_pct
                         FROM {TABLE} ORDER BY bodies DESC LIMIT 10""").fetchall():
    print(f"  {r[0]:<7}{r[1][:39]:<40}{r[2]:>14,}{r[3]:>10.4f}")
con.close()
print("\nDONE_BUILD_BODY_TYPE_CENSUS")

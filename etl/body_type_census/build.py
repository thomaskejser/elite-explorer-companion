import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (apply_comment_file, comment_file, connect, count_then_update,
                       prepare_table, report_merge, table_count)

HERE = pathlib.Path(__file__).resolve().parent

TABLE = "body_type_census"

con = connect()

before = prepare_table(con, TABLE, "spansh_body")

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

after = table_count(con, TABLE)
report_merge(TABLE, before, after, len(ins), upd, orphan)

apply_comment_file(con, comment_file(TABLE))

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

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (INPUT, apply_comment_file, comment_file, connect,
                       count_then_update, prepare_table, table_count)

TABLE = "body"
SRC = INPUT / "body.parquet"

if not SRC.exists():
    sys.exit(f"missing authoritative source {SRC}\n"
             f"seed it first with: python etl/body/build.py")

con = connect()
con.execute("CREATE SCHEMA IF NOT EXISTS staging")

before = prepare_table(con, TABLE, SRC.name)

con.execute(f"CREATE OR REPLACE TEMP TABLE src AS SELECT * FROM '{SRC.as_posix()}'")
n_src = table_count(con, 'src')
print(f"source {SRC.name}: {n_src} row(s)")

dup = con.execute("""SELECT type, body, count(*) FROM src
                     GROUP BY 1,2 HAVING count(*) > 1""").fetchall()
if dup:
    sys.exit(f"source has duplicate natural keys, refusing to merge: {dup}")

con.execute("""
CREATE OR REPLACE TEMP TABLE newrows AS
WITH missing AS (
  SELECT s.* FROM src s
  WHERE NOT EXISTS (SELECT 1 FROM body b
                    WHERE b.type = s.type AND b.body = s.body)
),
tagged AS (
  SELECT m.*,
         (m.body_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM body b WHERE b.body_id = m.body_id)
         ) AS keep_id
  FROM missing m
)
SELECT CASE WHEN keep_id THEN body_id
            ELSE (SELECT coalesce(max(body_id), 0) FROM body)
                 + row_number() OVER (ORDER BY body_id, type, body)
       END AS body_id,
       type, body, is_terraform_candidate, code,
       cr_value, cr_value_terraformable, value_formula, keep_id
FROM tagged
""")
con.execute("""
UPDATE newrows SET body_id = body_id -
    (SELECT count(*) FROM newrows n2 WHERE n2.keep_id AND n2.body_id < newrows.body_id)
WHERE NOT keep_id""")

ins = con.execute("""
INSERT INTO body (body_id, type, body, is_terraform_candidate, code, observed, bodies,
                  cr_value, cr_value_terraformable, value_formula)
SELECT body_id, type, body, is_terraform_candidate, code, false, 0,
       cr_value, cr_value_terraformable, value_formula FROM newrows
RETURNING body_id""").fetchall()
if ins:
    for r in con.execute("""SELECT body_id, type, body FROM body
            WHERE body_id IN (SELECT body_id FROM newrows) ORDER BY body_id""").fetchall():
        print(f"  INSERT body_id={r[0]:<4} {r[1]}/{r[2]}")

_W = """WHERE body.type = s.type AND body.body = s.body
  AND (body.is_terraform_candidate <> s.is_terraform_candidate
       OR body.code IS DISTINCT FROM s.code
       OR body.cr_value IS DISTINCT FROM s.cr_value
       OR body.cr_value_terraformable IS DISTINCT FROM s.cr_value_terraformable
       OR body.value_formula IS DISTINCT FROM s.value_formula)"""
upd = count_then_update(con,
    f"SELECT count(*) FROM body, src s {_W}",
    f"""UPDATE body SET is_terraform_candidate = s.is_terraform_candidate,
        code = s.code, cr_value = s.cr_value,
        cr_value_terraformable = s.cr_value_terraformable,
        value_formula = s.value_formula FROM src s {_W}""")

con.execute("""CREATE OR REPLACE TABLE staging.body_counts AS
    SELECT b.body_id, coalesce(count(s.sub_type), 0) AS n
    FROM body b LEFT JOIN spansh_body s
      ON s.sub_type = b.body AND lower(s.type) = b.type
    GROUP BY 1""")
_WS = """WHERE body.body_id = c.body_id
  AND (body.observed IS DISTINCT FROM (c.n > 0) OR body.bodies IS DISTINCT FROM c.n)"""
stats = count_then_update(con,
    f"SELECT count(*) FROM body, staging.body_counts c {_WS}",
    f"""UPDATE body SET observed = c.n > 0, bodies = c.n
        FROM staging.body_counts c {_WS}""")

orphan = con.execute("""SELECT body_id, type, body FROM body b
    WHERE NOT EXISTS (SELECT 1 FROM src s WHERE s.type=b.type AND s.body=b.body)
    ORDER BY body_id""").fetchall()

after = table_count(con, 'body')
print(f"\nmerged: {len(ins)} inserted, {upd} attribute update(s), "
      f"{stats} statistic update(s), {before} -> {after} rows")
if orphan:
    print(f"\n  {len(orphan)} row(s) in the table but NOT in the source -- left in "
          f"place, ids RETIRED (never reuse), deletion is a manual decision:")
    for r in orphan:
        print(f"    body_id={r[0]:<4} {r[1]}/{r[2]}")

apply_comment_file(con, comment_file(TABLE))

c = con.execute("""SELECT comment FROM duckdb_tables()
                   WHERE schema_name='main' AND table_name='body'""").fetchone()[0]
print(f"\n  comment re-asserted ({len(c or ''):,} chars)")
pk = con.execute("""SELECT constraint_text FROM duckdb_constraints()
        WHERE table_name='body' AND constraint_type='PRIMARY KEY'""").fetchone()
print(f"  {pk[0] if pk else 'NO PRIMARY KEY'}")
print(f"\n  {'id':>4}  {'type':<8}{'code':<22}{'body':<34}{'tf':>3}"
      f"{'bodies':>13}{'k':>12}{'k terraform':>13}")
for r in con.execute("""SELECT body_id, type, coalesce(code,''), body,
        is_terraform_candidate, bodies, observed, cr_value, cr_value_terraformable
        FROM body ORDER BY body_id""").fetchall():
    k = "  (none)" if r[7] is None else f"{r[7]:,.4f}"
    kt = "-" if r[8] is None else f"{r[8]:,.0f}"
    print(f"  {r[0]:>4}  {r[1]:<8}{r[2][:21]:<22}{r[3][:33]:<34}"
          f"{('Y' if r[4] else '-'):>3}{r[5]:>13,}{k:>12}{kt:>13}"
          f"{'' if r[6] else '   (unobserved)'}")

nk = con.execute("""SELECT count(*) FROM body
                    WHERE cr_value IS NULL OR value_formula IS NULL""").fetchone()[0]
print(f"\n  rows lacking a scan-value constant: {nk}"
      f"{'  <== every one of these will value as 0' if nk else '  (ok)'}")
con.close()
print("\nDONE_LOAD_BODY")

"""MERGE input/body.parquet into the `body` table. Never drops, never renumbers.

input/body.parquet is AUTHORITATIVE for the body-type dimension and is safe to
hand-edit. This script reconciles the table to it additively:

  * table created with CREATE TABLE IF NOT EXISTS -- never CREATE OR REPLACE, so
    the PRIMARY KEY and any foreign key pointing at body_id survive a reload.
  * matched on the NATURAL key (type, body), never on body_id. New entries get
    the parquet's body_id if that id is free, otherwise max+1.
  * existing rows keep their body_id forever. Renumbering would silently repoint
    every foreign key, and DuckDB will not warn you.
  * rows in the table but absent from the parquet are LEFT ALONE and reported.
    Their ids are retired, not reused -- deleting them is a manual decision,
    because something may already reference them.

SCAN VALUE. cr_value / cr_value_terraformable / value_formula are per-type
dimension attributes and live in input/body.parquet with everything else, so this
loader merges them like any other attribute. They are the `k` CONSTANT that feeds
Frontier's exploration formula, NOT a payout -- the payout needs the body's mass:

    planets:  base = max(k + k * mass_em^0.2 * 0.56591828, 500)
    stars:    base = k + solar_masses * k / 66.25

`observed` and `bodies` are DERIVED from spansh_body, not input: they are
statistics, not dimension attributes, so they are recomputed here on every run.
The copies inside the parquet are a point-in-time snapshot and are ignored on
load -- that is why a merge can report "updated" rows even when you have not
touched the file.

Usage:  python etl/load_body.py
        python etl/build_body.py --force   # to reseed the parquet itself
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common.db import (count_then_update, ROOT, INPUT, connect, ensure_columns, has_primary_key,
                       report_merge, comment_file, apply_comment_file)

TABLE = "body"
SRC = INPUT / "body.parquet"

if not SRC.exists():
    sys.exit(f"missing authoritative source {SRC}\n"
             f"seed it first with: python etl/build_body.py")

con = connect()
con.execute("CREATE SCHEMA IF NOT EXISTS staging")

# IF NOT EXISTS, never OR REPLACE. On an existing table this is a no-op and the
# PRIMARY KEY plus any inbound foreign keys are untouched.
con.execute("""
CREATE TABLE IF NOT EXISTS body (
    body_id                INTEGER NOT NULL PRIMARY KEY,
    type                   VARCHAR NOT NULL,
    body                   VARCHAR NOT NULL,
    is_terraform_candidate BOOLEAN NOT NULL,
    code                   VARCHAR,
    observed               BOOLEAN NOT NULL,
    bodies                 BIGINT  NOT NULL,
    cr_value               DOUBLE,
    cr_value_terraformable DOUBLE,
    value_formula          VARCHAR
)""")

# The scan-value columns arrived after the table did, so an existing database needs them
# ALTERed in. Declared nullable in BOTH places on purpose: ALTER TABLE ADD COLUMN ... NOT
# NULL cannot work on a table that already has rows, and a fresh CREATE must produce the
# identical shape. cr_value and value_formula are in practice always populated;
# cr_value_terraformable is genuinely NULL wherever no terraform bonus exists.
ensure_columns(con, "body", {"cr_value": "DOUBLE",
                             "cr_value_terraformable": "DOUBLE",
                             "value_formula": "VARCHAR"})

before = con.execute("SELECT count(*) FROM body").fetchone()[0]
print(f"table body: {before} existing row(s)")

con.execute(f"CREATE OR REPLACE TEMP TABLE src AS SELECT * FROM '{SRC.as_posix()}'")
n_src = con.execute("SELECT count(*) FROM src").fetchone()[0]
print(f"source {SRC.name}: {n_src} row(s)")

dup = con.execute("""SELECT type, body, count(*) FROM src
                     GROUP BY 1,2 HAVING count(*) > 1""").fetchall()
if dup:
    sys.exit(f"source has duplicate natural keys, refusing to merge: {dup}")

# --- allocate ids for genuinely new natural keys ----------------------------
# Honour the parquet's body_id when it is free; otherwise hand out max+1 so a
# hand-edited file with a colliding or blank id still merges safely.
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
# row_number() above is applied over ALL new rows, so ids stay unique even when
# some rows keep theirs; the gaps that creates are harmless.
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

# --- update dimension attributes of matched rows (never body_id) ------------
# No RETURNING: body is FK-referenced by system_known.primary_star_body_id and
# system_body.body_id, and DuckDB blocks UPDATE ... RETURNING on referenced rows.
# IS DISTINCT FROM, never <>: right after the scan-value migration these columns are
# NULL on every existing row, and `NULL <> 21790.0` is NULL, so a `<>` test would skip
# the backfill and leave them empty forever while still reporting a clean merge.
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

# --- recompute the derived statistics ---------------------------------------
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

after = con.execute("SELECT count(*) FROM body").fetchone()[0]
print(f"\nmerged: {len(ins)} inserted, {upd} attribute update(s), "
      f"{stats} statistic update(s), {before} -> {after} rows")
if orphan:
    print(f"\n  {len(orphan)} row(s) in the table but NOT in the source -- left in "
          f"place, ids RETIRED (never reuse), deletion is a manual decision:")
    for r in orphan:
        print(f"    body_id={r[0]:<4} {r[1]}/{r[2]}")

# The merge must re-assert the comment: a schema change is the one thing that can
# silently lose it, and comment_tables.py treats `body` as self-documented.
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

# A missing k is a silent wrong-answer generator downstream, so say so loudly.
nk = con.execute("""SELECT count(*) FROM body
                    WHERE cr_value IS NULL OR value_formula IS NULL""").fetchone()[0]
print(f"\n  rows lacking a scan-value constant: {nk}"
      f"{'  <== every one of these will value as 0' if nk else '  (ok)'}")
con.close()
print("\nDONE_LOAD_BODY")

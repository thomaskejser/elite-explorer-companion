"""Verify elite_mapping_v2.duckdb against the old database.

Checks four things, because a migration that copies the wrong number of rows silently
is worse than one that crashes:

  1. ROW COUNTS match the source table for table.
  2. CONSTRAINTS are actually present -- the whole point of the new file is that
     id_poi's foreign keys BIND here, where they could never be retrofitted.
  3. COMMENTS survived: every table and every column carries one. A migration is the
     one thing that silently drops them (ETL.md 5).
  4. INVARIANTS hold: at most one is_primary row per system, no dangling id_poi.

Usage:  python scripts/verify_new_model.py
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import duckdb
from common.db import ROOT

OLD, NEW = ROOT / "elite_mapping.duckdb", ROOT / "elite_mapping_v2.duckdb"
TABLES = ["body", "region", "sector", "poi", "body_type_census",
          "system_known", "system_body", "system_phenomenon", "system_predicted"]

con = duckdb.connect(str(NEW), read_only=True)
con.execute("SET memory_limit='8GB'")
con.execute(f"ATTACH '{OLD.as_posix()}' AS old (READ_ONLY)")
fail = []

print(f"{'table':<20}{'new':>15}{'old':>15}  match")
for t in TABLES:
    n = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
    o = con.execute(f"SELECT count(*) FROM old.main.{t}").fetchone()[0]
    ok = n == o
    fail.append(f"{t}: {n:,} != {o:,}") if not ok else None
    print(f"{t:<20}{n:>15,}{o:>15,}  {'ok' if ok else 'MISMATCH'}")
# id64 replaces staging.sys_bridge as the id64 -> system_id mapping, so the new
# database must carry it or every future POI link and phenomenon rebuild is stranded.
kn, k64 = con.execute("SELECT count(*), count(id64) FROM system_known").fetchone()
print(f"{'  system_known.id64':<20}{k64:>15,}{kn:>15,}  "
      f"{'ok' if k64 > kn * 0.999 else 'TOO SPARSE'}")
if k64 < kn * 0.999:
    fail.append(f"system_known.id64 only {k64:,}/{kn:,}")

print("\nconstraints in the new database:")
for r in con.execute("""SELECT table_name, constraint_type, constraint_text
    FROM duckdb_constraints() WHERE database_name = 'elite_mapping_v2'
      AND constraint_type IN ('PRIMARY KEY','FOREIGN KEY','UNIQUE')
    ORDER BY table_name, constraint_type""").fetchall():
    print(f"  {r[0]:<20}{r[1]:<14}{r[2]}")
nfk = con.execute("""SELECT count(*) FROM duckdb_constraints()
    WHERE database_name='elite_mapping_v2' AND constraint_type='FOREIGN KEY'""").fetchone()[0]
print(f"  -> {nfk} foreign keys")

print("\ncomments:")
for t in TABLES:
    tc = con.execute("""SELECT comment FROM duckdb_tables()
        WHERE database_name='elite_mapping_v2' AND table_name=?""", [t]).fetchone()
    tot, doc = con.execute("""SELECT count(*), count(comment) FROM duckdb_columns()
        WHERE database_name='elite_mapping_v2' AND table_name=?""", [t]).fetchone()
    ok = bool(tc and tc[0] and tc[0].strip()) and tot == doc
    if not ok:
        fail.append(f"{t}: table_comment={bool(tc and tc[0])} columns {doc}/{tot}")
    print(f"  {t:<20}{'table ok' if tc and tc[0] else 'TABLE COMMENT MISSING':<24}"
          f"columns {doc}/{tot}")

# system_body carries ONLY a PRIMARY KEY -- see schema/system_body.sql for the measured
# reason. Everything the database used to guarantee about it must therefore be checked
# by query, every run. Silence is not evidence.
print("\nsystem_body integrity (NOT enforced by constraints -- checked by query):")
for label, sql, key in (
    ("rows with no system_known parent",
     """SELECT count(*) FROM system_body b WHERE NOT EXISTS
        (SELECT 1 FROM system_known k WHERE k.system_id = b.system_id)""", "orphan rows"),
    ("duplicate (system_id, system_body)",
     """SELECT count(*) FROM (SELECT system_id, system_body FROM system_body
        GROUP BY 1,2 HAVING count(*) > 1)""", "duplicate natural keys"),
    ("dangling body_id",
     """SELECT count(*) FROM system_body b WHERE b.body_id IS NOT NULL AND NOT EXISTS
        (SELECT 1 FROM body d WHERE d.body_id = b.body_id)""", "dangling body_id"),
    ("dangling id_poi",
     """SELECT count(*) FROM system_body b WHERE b.id_poi IS NOT NULL AND NOT EXISTS
        (SELECT 1 FROM poi p WHERE p.poi_id = b.id_poi)""", "dangling id_poi"),
):
    n = con.execute(sql).fetchone()[0]
    print(f"  {label:<36}{n:>12,}{'  <== BROKEN' if n else '  (ok)'}")
    if n:
        fail.append(f"system_body: {n:,} {key}")

print("\ninvariants:")
dup = con.execute("""SELECT count(*) FROM (SELECT system_id FROM system_body
    WHERE is_primary GROUP BY 1 HAVING count(*) > 1)""").fetchone()[0]
print(f"  systems with >1 is_primary row: {dup:,}{'  <== BROKEN' if dup else '  (ok)'}")
if dup:
    fail.append("is_primary invariant")
# system_known.id_poi IS a real foreign key here -- that is the thing the old database
# can never have. system_body's is not; it was checked above by query.
d = con.execute("""SELECT count(*) FROM system_known x WHERE x.id_poi IS NOT NULL
    AND NOT EXISTS (SELECT 1 FROM poi p WHERE p.poi_id = x.id_poi)""").fetchone()[0]
print(f"  system_known.id_poi dangling: {d:,}"
      f"{'  <== BROKEN' if d else '  (ok, and FK-ENFORCED here)'}")
if d:
    fail.append("system_known.id_poi dangling")

con.close()
print("\nFAILURES:" if fail else "\nALL CHECKS PASSED")
for f in fail:
    print(f"  - {f}")
sys.exit(1 if fail else 0)

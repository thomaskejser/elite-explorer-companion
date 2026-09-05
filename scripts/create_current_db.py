"""Create elite_mapping_v2_current.duckdb and its complete schema. Run ONCE.

THE MODEL IS CREATED WHEN THE DATABASE IS MADE AND DOES NOT CHANGE AFTER THAT. Every
table is defined by schema/<table>.sql -- DDL and COMMENT ON together in one file.

Re-running is safe and does nothing: every CREATE is `CREATE TABLE IF NOT EXISTS` and
re-applying COMMENT ON is idempotent. That makes this also the way to re-assert comments
after any migration, which is the one thing a migration silently drops.

    python scripts/create_current_db.py           # create / re-assert
    python scripts/create_current_db.py --show    # what is in there now
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common.current import CURRENT_DB, CURRENT_TABLES, SCHEMA, connect

SHOW = "--show" in sys.argv

existed = CURRENT_DB.exists()
con = connect()
print(f"database: {CURRENT_DB.name}  ({'existing' if existed else 'CREATED'})\n")

if not SHOW:
    for table in CURRENT_TABLES:
        path = SCHEMA / f"{table}.sql"
        if not path.exists():
            raise SystemExit(f"missing schema file: {path}\n"
                             f"every table in CURRENT_TABLES needs schema/<table>.sql")
        con.execute(path.read_text(encoding="utf-8"))
        print(f"  applied  schema/{table}.sql")
    print()

# Verify rather than trust. A table with no comment is a table whose provenance will be
# guessed at in six months, and guessing about provenance is what has cost this project
# the most -- so an uncommented table fails the build here exactly as it does for the
# model.
rows = con.execute("""
    SELECT t.table_name, t.estimated_size, t.comment IS NOT NULL AS documented
    FROM duckdb_tables() t WHERE t.database_name = 'elite_mapping_v2_current'
    ORDER BY t.table_name""").fetchall()
print(f"  {'table':<22}{'rows':>12}  documented")
undocumented, uncommented_cols = [], []
for name, size, doc in rows:
    print(f"  {name:<22}{size:>12,}  {'yes' if doc else '*** NO ***'}")
    if not doc:
        undocumented.append(name)
    missing = con.execute("""
        SELECT column_name FROM duckdb_columns()
        WHERE table_name = ? AND comment IS NULL ORDER BY column_index""",
        [name]).fetchall()
    uncommented_cols += [f"{name}.{c[0]}" for c in missing]

for name, _, _ in rows:
    pk = con.execute("""SELECT constraint_text FROM duckdb_constraints()
                        WHERE table_name = ? AND constraint_type = 'PRIMARY KEY'""",
                     [name]).fetchone()
    print(f"  {name:<22}{pk[0] if pk else '*** no primary key ***'}")

if undocumented or uncommented_cols:
    print(f"\nUNDOCUMENTED -- tables: {undocumented or 'none'}")
    print(f"                columns: {uncommented_cols or 'none'}")
    raise SystemExit("every table AND column needs a COMMENT ON. See ETL.md.")

print("\nDONE_CREATE_CURRENT_DB")

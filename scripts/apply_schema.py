"""Apply schema/<name>.sql to the model database. Views live here, not in etl/.

A view stores nothing, so it has no builder and no merge: its whole definition is its
schema file. This applies one or more of them and re-asserts the comments, which
CREATE OR REPLACE VIEW silently drops.

    python scripts/apply_schema.py system_all
    ELITE_DB=... python scripts/apply_schema.py system_all
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common.db import connect
from common.current import SCHEMA

names = [a for a in sys.argv[1:] if not a.startswith("-")]
if not names:
    raise SystemExit("usage: python scripts/apply_schema.py <name> [<name> ...]")

con = connect()
for name in names:
    path = SCHEMA / f"{name}.sql"
    if not path.exists():
        raise SystemExit(f"no such schema file: {path}")
    con.execute(path.read_text(encoding="utf-8"))
    print(f"applied {path.name}")

    is_view = con.execute("SELECT count(*) FROM duckdb_views() WHERE view_name = ?",
                          [name]).fetchone()[0]
    if not is_view:
        continue
    # CREATE OR REPLACE VIEW drops every COMMENT ON, so the file must carry them all and
    # this is the only thing that checks it did.
    missing = [r[0] for r in con.execute(
        """SELECT column_name FROM duckdb_columns()
           WHERE table_name = ? AND comment IS NULL ORDER BY column_index""",
        [name]).fetchall()]
    if missing or not con.execute(
            "SELECT comment FROM duckdb_views() WHERE view_name = ?",
            [name]).fetchone()[0]:
        raise SystemExit(f"{name}: missing comment on {missing or 'the view itself'} -- "
                         f"CREATE OR REPLACE VIEW drops comments, so they must all be "
                         f"in {path.name}")
    cols = len(con.execute(f"DESCRIBE {name}").fetchall())
    print(f"  comments: view + all {cols} columns")

print("\nDONE_APPLY_SCHEMA")

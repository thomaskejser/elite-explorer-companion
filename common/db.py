"""Shared DuckDB plumbing for the etl/ scripts. See ETL.md for the conventions.

Anything used by more than one etl script belongs here rather than being copied.
Import it from an etl script like this:

    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    from common.db import ROOT, connect, ensure_columns, report_merge
"""
import pathlib

import duckdb

ROOT = pathlib.Path(__file__).resolve().parent.parent
DB = ROOT / "elite_mapping.duckdb"
INPUT = ROOT / "input"
# Per-table COMMENT ON scripts: schema/<table>_comment.sql
SCHEMA = ROOT / "schema"

# 6GB, not more: the Spansh parser OOMs above this on a 569M-row scan, and these
# scripts touch the same table.
MEMORY_LIMIT = "6GB"
THREADS = 8
# DuckDB must have somewhere to spill: without this a large sort or aggregate
# raises OutOfMemoryError instead of going to disk. Deliberately outside the
# project tree. The machine has 33.5GB RAM and 16 cores, so the 6GB default is a
# Spansh-parser constraint (see the ingest runbook), not a limit these loads need --
# pass memory_limit= for heavy jobs.
TEMP_DIR = pathlib.Path(r"C:/Users/thoma/AppData/Local/Temp/claude/C--Source-elite-mapping/809aa2a8-b7f0-476d-a686-8010afa00043/scratchpad/duck_tmp")


def connect(read_only=False, memory_limit=MEMORY_LIMIT, threads=THREADS):
    """Open elite_mapping.duckdb with the settings every script needs.

    preserve_insertion_order=false matters on the big tables -- without it a
    569M-row aggregate buffers far more than the memory limit allows.
    """
    con = duckdb.connect(str(DB), read_only=read_only)
    con.execute(f"SET memory_limit='{memory_limit}'")
    con.execute(f"SET threads={threads}")
    con.execute("SET preserve_insertion_order=false")
    # The progress bar emits thousands of carriage-return updates,
    # which wrecks piped or captured output.
    con.execute("SET enable_progress_bar=false")
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    con.execute(f"SET temp_directory='{TEMP_DIR.as_posix()}'")
    con.execute("SET max_temp_directory_size='400GB'")
    return con


def ensure_columns(con, table, columns):
    """Additively migrate a table to have `columns` -- {name: sql_type}.

    ETL.md forbids dropping a table to change its shape, so new columns are ALTERed
    in. Idempotent. Returns the list of names actually added.

    CANNOT retrofit constraints: DuckDB has no ALTER TABLE ADD PRIMARY KEY, so a
    table created before its builder declared a key stays unconstrained. Callers
    that care should check duckdb_constraints() and say so.
    """
    have = {r[0] for r in con.execute(f"DESCRIBE {table}").fetchall()}
    added = []
    for name, decl in columns.items():
        if name not in have:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
            added.append(name)
            print(f"  MIGRATE {table}: added column {name} {decl}")
    return added


def has_primary_key(con, table):
    """The PRIMARY KEY constraint text for `table`, or None."""
    r = con.execute("""SELECT constraint_text FROM duckdb_constraints()
                       WHERE table_name = ? AND constraint_type = 'PRIMARY KEY'""",
                    [table]).fetchone()
    return r[0] if r else None


def report_merge(table, before, after, inserted, updated, orphans, extra=""):
    """Print the standard merge summary. A no-op run must LOOK like a no-op."""
    print(f"\nmerged {table}: {inserted} inserted, {updated} updated{extra}, "
          f"{before} -> {after} rows")
    if orphans:
        print(f"  {len(orphans)} row(s) present in the table but NOT produced by the "
              f"source -- LEFT IN PLACE, keys RETIRED (never reuse). Deleting one is "
              f"a manual decision, because something may already reference it:")
        for o in orphans:
            print(f"    {o}")


def count_then_update(con, count_sql, update_sql):
    """Run an UPDATE and return how many rows it changed -- WITHOUT using RETURNING.

    *** DuckDB blocks `UPDATE ... RETURNING` when the updated row is referenced by a
    foreign key *** with "key ... is still referenced by a foreign key in a different
    table", even though the identical UPDATE without RETURNING succeeds and even though
    the key value is not changing. Verified directly: WHERE-literal, UPDATE...FROM and
    correlated-subquery forms all work; adding RETURNING to any of them fails.

    So the merge pattern cannot use RETURNING to count updates on any table that has an
    inbound FK -- which is every dimension once system_known and system_body exist. Count
    with a SELECT carrying the SAME predicate, then update. `count_sql` must mirror
    `update_sql`'s WHERE clause or the reported number will be wrong.
    """
    n = con.execute(count_sql).fetchone()[0]
    if n:
        con.execute(update_sql)
    return n


def comment_file(table):
    """Path to a table's canonical COMMENT script: schema/<table>_comment.sql."""
    return SCHEMA / f"{table}_comment.sql"


def apply_comment_file(con, path):
    """Run a *_comment.sql file. Must be re-asserted after any schema change --
    that is the one thing a migration silently loses, and comment_tables.py only
    verifies self-documented tables are non-empty rather than rewriting them."""
    con.execute(pathlib.Path(path).read_text(encoding="utf-8"))

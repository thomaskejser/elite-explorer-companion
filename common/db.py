"""Shared DuckDB plumbing for the etl/ scripts. See ETL.md for the conventions.

Anything used by more than one etl script belongs here rather than being copied.
Import it from an etl script like this:

    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    from common.db import ROOT, connect, assert_shape, report_merge
"""
import os
import pathlib
import re

import duckdb

ROOT = pathlib.Path(__file__).resolve().parent.parent
# Override with ELITE_DB to run the same scripts against elite_mapping_v2.duckdb, where
# the raw provider snapshots live in the `staging` schema rather than in `main`.
DB = pathlib.Path(os.environ.get("ELITE_DB") or (ROOT / "elite_mapping.duckdb"))
INPUT = ROOT / "input"
# Per-table DDL + COMMENT ON, one file each: schema/<table>.sql
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

    # RAW SNAPSHOTS LIVE IN `staging`, THE MODEL LIVES IN `main`. The pipeline is
    # download -> staging -> merge -> main, so a builder reads staging and writes main.
    #
    # search_path resolves both, which is why no builder had to be rewritten to say
    # `staging.spansh_body`: an unqualified name is found in whichever schema has it.
    # `main` is FIRST and that matters -- it is the default for CREATE, so anything a
    # script creates without a schema still lands in main, and a model table always
    # wins a name lookup against a staging table of the same name.
    #
    # In the old database the raw tables are in `main` too, so this is a no-op there
    # and the same scripts work against both.
    con.execute("SET search_path='main,staging'")
    return con


def expected_columns(table):
    """Column names schema/<table>.sql declares, in order.

    Parsed from the CREATE block: every line up to the first table-level constraint is
    a column, and the first token on it is its name. The DDL file is the ONE definition
    of the table shape, so this is what "correct" means.
    """
    sql = comment_file(table).read_text(encoding="utf-8")
    body = re.search(r"CREATE TABLE IF NOT EXISTS \w+\s*\((.*?)\n\);", sql, re.S)
    if not body:
        raise SystemExit(f"cannot find a CREATE block in {comment_file(table)}")
    out = []
    for line in body.group(1).split("\n"):
        line = line.strip()
        if not line or line.startswith("--"):
            continue
        head = line.split()[0].upper()
        if head in ("PRIMARY", "UNIQUE", "FOREIGN", "CONSTRAINT", "CHECK"):
            continue
        # `x DOUBLE, y DOUBLE, z DOUBLE,` -- several columns on one line
        for part in line.split(","):
            part = part.strip()
            if part and not part.split()[0].upper() in (
                    "PRIMARY", "UNIQUE", "FOREIGN", "CONSTRAINT", "CHECK"):
                name = part.split()[0].strip('"')
                if name and name not in out:
                    out.append(name)
    return out


def assert_shape(con, table):
    """Fail unless `table` matches schema/<table>.sql exactly.

    *** THE MODEL IS CREATED WITH THE DATABASE AND NEVER ALTERED AFTERWARDS. *** This
    replaces the old ensure_columns() migrate-in-place approach, and the reason is
    everything that approach cost us: DuckDB has no ALTER TABLE ADD CONSTRAINT, so any
    column added after creation could never carry a PRIMARY KEY, UNIQUE or FOREIGN KEY.
    system_known.id_poi sat as an unenforced integer for exactly that reason, and every
    builder grew a CORE/ADDITIVE split plus a drift guard to work around it.

    Now the shape comes from one place, binds all of its constraints at CREATE, and a
    mismatch is an ERROR rather than a silent migration. To change a table: edit
    schema/<table>.sql and build a new database with scripts/migrate_new_model.py.
    """
    want = expected_columns(table)
    have = [r[0] for r in con.execute(f"DESCRIBE {table}").fetchall()]
    if have == want:
        return
    missing = [c for c in want if c not in have]
    extra = [c for c in have if c not in want]
    raise SystemExit(
        f"{table} does not match schema/{table}.sql.\n"
        f"  missing: {missing or 'none'}\n"
        f"  unexpected: {extra or 'none'}\n"
        f"  order differs: {have != want and not missing and not extra}\n"
        f"The model is created with the database and is NOT migrated in place. Edit "
        f"schema/{table}.sql and rebuild with scripts/migrate_new_model.py --fresh.")



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
    """Path to a table's canonical schema file: schema/<table>.sql.

    DDL and COMMENT ON live in the SAME file so a schema change and its documentation
    cannot drift apart. Applying it is safe at any time: the CREATE is
    `CREATE TABLE IF NOT EXISTS`, a no-op on an existing table, so re-asserting the
    comments after a merge costs nothing and cannot reshape anything.
    """
    return SCHEMA / f"{table}.sql"


def apply_comment_file(con, path):
    """Run a schema/<table>.sql file. Must be re-asserted after any schema change --
    that is the one thing a migration silently loses, and comment_tables.py only
    verifies self-documented tables are non-empty rather than rewriting them."""
    con.execute(pathlib.Path(path).read_text(encoding="utf-8"))

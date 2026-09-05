"""Shared DuckDB plumbing for the etl/ scripts. See ETL.md for the conventions.

Anything used by more than one etl script belongs here rather than being copied.
Import it from an etl script like this:

    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    from common.db import ROOT, connect, comment_file, report_merge
"""
import os
import pathlib

import duckdb

ROOT = pathlib.Path(__file__).resolve().parent.parent
# THE MODEL DATABASE. Override with ELITE_DB to point at another file.
#
# *** Read at IMPORT time. *** Setting os.environ["ELITE_DB"] after importing this
# module has no effect -- see the note in ETL.md. common/current.py opens its file by
# path for exactly that reason.
DB = pathlib.Path(os.environ.get("ELITE_DB") or (ROOT / "elite_mapping_v2.duckdb"))
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
    """Open the model database with the settings every script needs.

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
    # search_path resolves both, so an unqualified name is found in whichever schema
    # has it. `main` is FIRST and that matters -- it is the default for CREATE, so
    # anything a script creates without a schema still lands in main, and a model table
    # always wins a name lookup against a staging table of the same name.
    con.execute("SET search_path='main,staging'")
    return con


def staged(con, role, required=True):
    """Resolve a ROLE to the staging table that currently fills it.

    Staging tables are named after the DOWNLOAD (staging.spansh_galaxy_1day_body,
    staging.edsm_bodies7days), not after the role they play, so that a 7-day slice can
    never be mistaken for a full catalogue by reading its name. The merge therefore
    cannot hardcode a table name -- it asks for a role and gets whatever was most
    recently staged for it, full dump or delta alike.

    scripts/ingest_sources.py writes (role, staging_table) into
    staging.ingest_manifest on every ingest; this reads the newest row.

    Falls back to a table literally named `role` when the manifest has no entry, which
    is what a database migrated before the manifest existed looks like.
    """
    has_manifest = con.execute(
        """SELECT count(*) FROM duckdb_tables()
           WHERE schema_name='staging' AND table_name='ingest_manifest'"""
    ).fetchone()[0]
    if has_manifest:
        r = con.execute(
            """SELECT staging_table FROM staging.ingest_manifest
               WHERE role = ? ORDER BY ingested_at_utc DESC LIMIT 1""", [role]
        ).fetchone()
        if r and con.execute(
                """SELECT count(*) FROM duckdb_tables()
                   WHERE schema_name='staging' AND table_name = ?""",
                [r[0]]).fetchone()[0]:
            return f"staging.{r[0]}"
    if con.execute("""SELECT count(*) FROM duckdb_tables() WHERE table_name = ?""",
                   [role]).fetchone()[0]:
        return role
    if required:
        raise SystemExit(
            f"no staged table for role '{role}'. Run:\n"
            f"    python scripts/ingest_sources.py --incremental --only {role}\n"
            f"or --full. `python scripts/ingest_sources.py --list` shows what is staged.")
    return None


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
    the key value is not changing. WHERE-literal, UPDATE...FROM and correlated-subquery
    forms all work; adding RETURNING to any of them fails.

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
    that is the one thing a migration silently loses, and nothing else re-applies it."""
    con.execute(pathlib.Path(path).read_text(encoding="utf-8"))


def table_count(con, table):
    """Rows in a table right now. Accepts a qualified name (`staging.src_body`)."""
    return con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def prepare_table(con, table, source=None):
    """Apply schema/<table>.sql, then report what the table already holds.

    The two things every builder and loader does before it touches anything: assert the
    DDL and its COMMENT ON text (CREATE TABLE IF NOT EXISTS, so a no-op on an existing
    table), and read the row count that `report_merge` will later compare against.
    `source` names where the incoming rows come from, for the one line this prints.
    """
    apply_comment_file(con, comment_file(table))
    before = table_count(con, table)
    print(f"{table}: {before:,} row(s) before"
          + (f"; source {source}" if source else ""))
    return before

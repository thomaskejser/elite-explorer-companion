"""Shared DuckDB plumbing for the etl/ scripts. See ETL.md for the conventions.

Anything used by more than one etl script belongs here rather than being copied.
Import it from an etl script like this:

    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    from common.db import ROOT, connect, comment_file, report_merge
"""
import os
import pathlib
import string

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
STAGING_SCHEMA = SCHEMA / "staging"
TRANSFORM_SCHEMA = SCHEMA / "transform"
MACRO_SCHEMA = SCHEMA / "macro"

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


def connect(read_only=False, memory_limit=MEMORY_LIMIT, threads=THREADS, path=None):
    """Open the model database with the settings every script needs.

    preserve_insertion_order=false matters on the big tables -- without it a
    569M-row aggregate buffers far more than the memory limit allows.
    """
    con = duckdb.connect(str(path or DB), read_only=read_only)
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
    if not read_only:
        con.execute("CREATE SCHEMA IF NOT EXISTS staging")
    con.execute("SET search_path='main,staging'")
    if not read_only:
        apply_macros(con)
    return con


def apply_macros(con):
    for path in sorted(MACRO_SCHEMA.glob("*.sql")):
        run_sql_file(con, path)


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


MANIFEST = """CREATE TABLE IF NOT EXISTS staging.ingest_manifest (
    role VARCHAR, staging_table VARCHAR, source_url VARCHAR, raw_file VARCHAR,
    raw_bytes BIGINT, row_count BIGINT, is_delta BOOLEAN,
    ingested_at_utc TIMESTAMPTZ, note VARCHAR)"""


def record_ingest(con, role, table, url, path, rows, is_delta, note):
    """Write the (role, staging_table) provenance row `staged()` later reads back."""
    import datetime
    con.execute(MANIFEST)
    con.execute("DELETE FROM staging.ingest_manifest WHERE role=? AND staging_table=?",
                [role, table])
    raw = pathlib.Path(path) if path else None
    con.execute("INSERT INTO staging.ingest_manifest VALUES (?,?,?,?,?,?,?,?,?)",
                [role, table, url, str(path) if path else None,
                 raw.stat().st_size if raw and raw.exists() else None,
                 rows, is_delta,
                 datetime.datetime.now(datetime.timezone.utc), note])


def bind_role(con, role, table):
    """Point staging.<role> at `table` as a VIEW, so static SQL can name the role.

    The physical table is named after the DOWNLOAD, which is what stops a delta being
    misread as a catalogue -- but that name changes with the window, and a .sql file
    cannot interpolate. The role name is therefore a view over whichever table currently
    fills it, and staging.ingest_manifest says which one that is.

    A role-named TABLE left from before the views existed is renamed aside rather than
    dropped: it is the FULL catalogue, and a delta must never quietly destroy it.
    """
    if table == role:
        return role
    if con.execute("""SELECT count(*) FROM duckdb_tables()
                      WHERE schema_name='staging' AND table_name = ?""",
                   [role]).fetchone()[0]:
        con.execute(f"DROP TABLE IF EXISTS staging.{role}_superseded")
        con.execute(f"ALTER TABLE staging.{role} RENAME TO {role}_superseded")
        print(f"    kept the previous staging.{role} as staging.{role}_superseded "
              f"({table_count(con, f'staging.{role}_superseded'):,} rows)")
    con.execute(f"CREATE OR REPLACE VIEW staging.{role} AS SELECT * FROM staging.{table}")
    return table


def is_delta_window(window):
    return window != "full"


WINDOW_SPAN_DAYS = {"1day": 1.0, "7days": 7.0, "1month": 30.0, "full": float("inf")}


def window_for_gap(feed, gap_days):
    """The NARROWEST window `feed` publishes that spans `gap_days`, or its widest.

    The counterpart to window_covering, and it points the other way on purpose. An
    explicit --window is a BUDGET, so it never fetches more than it was asked for. An
    automatic window is a REQUIREMENT computed from how far behind the model actually is
    -- max(system_known.first_seen) against now -- and a dump narrower than the gap would
    leave a hole nothing later fills, because tomorrow's delta only reaches back a day.
    """
    for w, span in sorted(WINDOW_SPAN_DAYS.items(), key=lambda kv: kv[1]):
        if w in feed and span >= gap_days:
            return w
    return max((w for w in feed), key=lambda w: WINDOW_SPAN_DAYS[w])


def model_gap_days(con, table="system_known", column="first_seen"):
    """Days since this model last inserted a row, or None when it never has.

    None means "no floor on how far back to look" and the caller should take the full
    catalogue. A load that inserts nothing leaves this growing, which is the conservative
    direction: it asks for a wider dump rather than silently skipping a window.
    """
    if not con.execute("""SELECT count(*) FROM duckdb_columns()
                          WHERE schema_name='main' AND table_name = ? AND
                                column_name = ?""", [table, column]).fetchone()[0]:
        return None
    r = con.execute(f"SELECT date_diff('second', max({column}), now()) / 86400.0 "
                    f"FROM main.{table}").fetchone()[0]
    return None if r is None else max(float(r), 0.0)


def window_covering(feed, order, want):
    """The WIDEST window `feed` publishes that is no wider than `want`, or None.

    Only Spansh publishes every width. EDSM has 7days and full, EDAstro has 7days and
    nothing else, so one --window means a different file per provider -- and it must
    never mean a BIGGER one. Asking for a day and being handed EDSM's 97M-row full dump
    is not a delta refresh, it is a different job with a different cost, so a provider
    with nothing narrow enough is SKIPPED and the run says so. Ask for the wider dump by
    asking for it.
    """
    rank = list(order)
    available = [w for w in rank[:rank.index(want) + 1] if w in feed]
    return available[-1] if available else None


def stage_json(con, table, schema_name, fields, select_sql):
    """Rebuild staging.<table> from schema/staging/<schema_name>.sql and populate it.

    Build-aside-and-swap, so a failed parse leaves the previous snapshot untouched:
    the new rows land in a __new table and the old one is dropped only once they are
    all in. That is what makes rebuilding a RAW SOURCE table safe here -- the download
    it is rebuilt from is on disk in the same run, so nothing costs a re-download, and
    the alternative is a table whose shape can never be corrected.
    """
    tmp = f"{table}__new"
    con.execute(f"DROP TABLE IF EXISTS staging.{tmp}")
    run_staging_template(con, schema_name, table=tmp, **fields)
    con.execute(f"INSERT INTO staging.{tmp} BY NAME {select_sql}")
    con.execute(f"DROP TABLE IF EXISTS staging.{table}")
    con.execute(f"ALTER TABLE staging.{tmp} RENAME TO {table}")
    run_staging_template(con, schema_name, table=table, **fields)
    return table_count(con, f"staging.{table}")


def staged_source(con, role):
    """(staging_table, is_delta, ingested_at_utc, row_count) behind a role, or None.

    What a loader PRINTS before it merges. `staged()` answers "which table"; this
    answers "and what window is it, staged when" -- the provenance line that stops a
    delta being read as a census.
    """
    if not con.execute("""SELECT count(*) FROM duckdb_tables()
                          WHERE schema_name='staging'
                            AND table_name='ingest_manifest'""").fetchone()[0]:
        return None
    return con.execute(
        """SELECT staging_table, is_delta, ingested_at_utc, row_count
           FROM staging.ingest_manifest WHERE role = ?
           ORDER BY ingested_at_utc DESC LIMIT 1""", [role]).fetchone()


# Child -> parent for every reference the model has. This is the ONLY record of which
# column points at what, so a new one must be added here or nothing knows it exists.
# A table that leaves the model must leave this list too: check_references() would
# otherwise fail on a table that is not there.
REFERENCES = [
    ("carrier",           "system_id",            "system_known", "system_id"),
    ("carrier_position",  "callsign",             "carrier",      "callsign"),
    ("sector",            "region_id",            "region",       "region_id"),
    ("system_catalog",    "system_id",            "system_known", "system_id"),
    ("system_known",      "sector_id",            "sector",       "sector_id"),
    ("system_known",      "region_id",            "region",       "region_id"),
    ("system_known",      "primary_star_body_id", "body",         "body_id"),
    ("system_known",      "id_poi",               "poi",          "poi_id"),
    ("system_body",       "id_poi",               "poi",          "poi_id"),
    ("system_phenomenon", "system_id",            "system_known", "system_id"),
    ("system_poi",        "poi_id",               "poi",          "poi_id"),
    ("station_service",   "system_id",            "system_known", "system_id"),
]


def dangling(con, child, column, parent, parent_column):
    return con.execute(f"""
        SELECT count(*) FROM {child} c
        WHERE c.{column} IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM {parent} p
                          WHERE p.{parent_column} = c.{column})""").fetchone()[0]


def check_references(con, table=None, fail=False):
    checks = [r for r in REFERENCES if table is None or r[0] == table]
    if not checks:
        return 0
    total = 0
    for child, column, parent, parent_column in checks:
        n = dangling(con, child, column, parent, parent_column)
        total += n
        flag = "" if not n else "   <== DANGLING"
        print(f"  {child}.{column} -> {parent}.{parent_column}: {n:,}{flag}")
    if total and fail:
        raise SystemExit(f"{total:,} dangling reference(s) -- refusing to finish")
    return total


def has_primary_key(con, table):
    """The PRIMARY KEY constraint text for `table`, or None."""
    r = con.execute("""SELECT constraint_text FROM duckdb_constraints()
                       WHERE table_name = ? AND constraint_type = 'PRIMARY KEY'""",
                    [table]).fetchone()
    return r[0] if r else None


def merge_counts(con, path):
    """Rows a MERGE is about to insert and update, counted BEFORE it runs.

    `MERGE ... RETURNING` cannot be used on any table a foreign key points at: DuckDB
    raises "key ... is still referenced by a foreign key in a different table" the moment
    a matched row is actually written. The counts therefore come from a `counts.sql`
    beside the `load.sql`, whose predicates MUST mirror it -- `report_merge` cross-checks
    the insert count against the row-count delta and says so when they disagree.
    """
    return run_sql_file(con, path).fetchone()


def report_merge(table, before, after, inserted, updated, orphans, extra=""):
    """Print the standard merge summary. A no-op run must LOOK like a no-op."""
    print(f"\nmerged {table}: {inserted} inserted, {updated} updated{extra}, "
          f"{before} -> {after} rows")
    if after - before != inserted:
        print(f"  ! counts.sql predicted {inserted} insert(s) but the table grew by "
              f"{after - before} -- its predicates have drifted from load.sql's")
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


def staging_file(table):
    return STAGING_SCHEMA / f"{table}.sql"


def transform_file(table):
    return TRANSFORM_SCHEMA / f"{table}.sql"


def run_sql_file(con, path, params=None):
    sql = pathlib.Path(path).read_text(encoding="utf-8")
    return con.execute(sql, params) if params is not None else con.execute(sql)


def run_staging_template(con, name, **fields):
    """Apply schema/staging/<name>.sql with ${placeholders} filled in.

    A windowed source stages into a table NAMED AFTER THE DOWNLOAD
    (staging.spansh_galaxy_1day_system), so one download has as many physical table
    names as it has windows and a per-name .sql file would be the same DDL and the same
    column comments written out four times. The file carries ${table} and ${provenance}
    instead and is filled in here -- ONE definition, and the window still says itself in
    the table name and in the table comment.
    """
    sql = string.Template(staging_file(name).read_text(encoding="utf-8"))
    return con.execute(sql.substitute(**fields))


def apply_comment_file(con, path):
    """Run a schema/<table>.sql file. Must be re-asserted after any schema change --
    that is the one thing a migration silently loses, and nothing else re-applies it."""
    run_sql_file(con, path)


def table_count(con, table):
    """Rows in a table right now. Accepts a qualified name (`staging.primary_star`)."""
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

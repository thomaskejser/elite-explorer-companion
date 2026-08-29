"""Shared plumbing for elite_mapping_v2_current.duckdb -- the APP-STATE database.

Two databases, two jobs, and keeping them apart is the point:

  elite_mapping_v2.duckdb          the MODEL. What the galaxy is, merged from Spansh,
                                   EDSM, EDAstro and Canonn. 60 GiB, rebuilt by etl/.
  elite_mapping_v2_current.duckdb  what THIS COMMANDER has done. Megabytes, appended to
                                   by the overlay while you fly, never rebuilt.

The model is reproducible from its sources; this is not. Losing the model costs a
re-ingest, losing this costs every hour actually spent flying -- which is why it is a
separate file rather than more schemas in the big one, and why every loader here MERGES
and never CREATE OR REPLACEs.

*** THE WRITE BOUNDARY: THE APP WRITES TO elite_mapping_v2_current.duckdb AND NOTHING
ELSE. *** The model database is BACKGROUND INFORMATION -- the app reads it and may
never write to it, in any schema, under any circumstance. Three reasons this is a rule
and not a preference:

  1. The model is derived. Every row in it is reproducible from input/ and raw/ by
     re-running etl/. A row the app wrote would be the one exception, and the next
     rebuild would erase it with no warning and no way to tell it had gone.
  2. The app runs while you fly. It is a live HUD reacting to journal events, and the
     model is a 60 GiB file that a merge may be halfway through rewriting. A writer
     holding it open is a writer blocking the pipeline, or losing to it.
  3. Provenance. "Where did this fact come from" must have one answer per database:
     the model says what the galaxy is according to Spansh/EDSM/EDAstro/Canonn, this
     says what one commander did. Mixing the two makes both unciteable.

The rule is ENFORCED, not merely documented: attach_model() attaches READ_ONLY, so an
accidental write raises rather than lands. Nothing in this module can open the model
any other way. When the app needs to record something -- a visit, a reveal, a POI
sighting, a correction -- the answer is always a table HERE, never a column there.

Cross-database foreign keys do not exist in DuckDB, so id64 on these tables is a JOIN
KEY and nothing more: nothing enforces it and NULL is a normal, expected value. That is
a direct consequence of the split above and not a shortcoming of it -- the app cannot
depend on the model being present, let alone consistent, at the moment it writes.
"""
import os
import pathlib

import duckdb

from common.db import ROOT, TEMP_DIR

# The model database, ATTACHed read-only only when a loader needs to resolve id64.
MODEL_DB = pathlib.Path(os.environ.get("ELITE_MODEL_DB")
                        or (ROOT / "elite_mapping_v2.duckdb"))
CURRENT_DB = ROOT / "elite_mapping_v2_current.duckdb"
SCHEMA = ROOT / "schema"          # flat, shared with the model: schema/<table>.sql
# WHERE THE HAND-WRITTEN JSON STORES LIVE -- the flight history that predates these
# tables and is NOT reproducible from anything. Read by the three loaders that migrate
# it (load_system_seen, load_system_confirmed, load_poi_visited) and by nothing else.
#
# *** NOT app/. *** That directory is now the OVERLAY PACKAGE, and this used to point
# at it back when the app kept its state in JSON beside its code. A loader resolving
# "app/confirmed.json" today would be looking for data inside a Python package, which
# is both wrong and the kind of wrong that fails silently as "0 rows to migrate".
STORES = ROOT / "input" / "unmigrated"

# WHICH TABLES BELONG TO THIS DATABASE. schema/ is one flat directory shared with the
# model, so the filename cannot say which database a table lives in -- this list is the
# only thing that does. Order is load order. Add a table here or create_current_db.py
# will not build it, and no error will tell you: an unlisted schema file is simply a
# file nobody reads.
CURRENT_TABLES = ["system_seen", "system_visited", "system_confirmed", "poi_visited",
                  "system_wrong"]


def sector_sql(name_expr):
    """SQL deriving the procedural sector from a system-name expression.

    THE ONE DEFINITION. Every app-state table stores `sector` and every writer -- the
    overlay, all four loaders, the rebuild script -- fills it through this, so the
    column cannot mean different things in different rows.

    A procedural name is `<Sector> <AA-A> <mass_code><n>[-<n>]`, so the sector is
    everything before the first boxel token. Returns NULL for a hand-named system
    (Sol, Achenar), which is correct and not a failure: named space is the inhabited
    bubble, and the bubble holds no predictions.

    VALIDATED, not assumed: agrees with the model's own system_predicted.sector on
    50,000 sampled rows (0 mismatches) and with app.names.sector_of on every
    app-state name (0 mismatches). app/names.py holds the Python twin, used for the
    live "which sector am I in" decision where no database is in hand; the two must
    stay in step.
    """
    return (r"nullif(regexp_extract({}, '^(.*) [A-Z][A-Z]-[A-Z] [a-h]\d', 1), '')"
            .format(name_expr))


def connect(read_only=False):
    """Open the APP-STATE database. Always CURRENT_DB -- never the model.

    *** This deliberately does NOT go through common.db.connect(). *** That function
    resolves its target from the ELITE_DB environment variable AT IMPORT TIME, so a
    caller that sets ELITE_DB after importing it silently gets whatever ELITE_DB said
    earlier -- which, on the first run of this module, meant creating the app-state
    tables inside the model database instead. Opening the path directly removes
    the ordering hazard entirely: there is no environment variable to get wrong.

    THE TABLES HERE ARE TINY, BUT THIS CONNECTION IS NOT ONLY USED FOR THEM. The
    overlay attaches the model to it and reads system_predicted (2.27M rows),
    system_neutron (3.4M) and carrier joined against system_known (197.6M) through this
    very handle, on every jump. The settings below were once justified by "a few
    thousand rows" and stopped being true when that started; threads=4 on a 16-core
    machine measured 87 ms against 46 ms for the same neutron query. Eight is a
    deliberate middle: the queries are short bursts and the machine is also running a
    game, so taking every core would be rude.
    """
    con = duckdb.connect(str(CURRENT_DB), read_only=read_only)
    con.execute("SET memory_limit='4GB'")
    con.execute("SET threads=8")
    con.execute("SET preserve_insertion_order=false")
    con.execute("SET enable_progress_bar=false")
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    con.execute(f"SET temp_directory='{TEMP_DIR.as_posix()}'")
    return con


def attach_model(con, alias="model"):
    """ATTACH the model database READ-ONLY, for id64 resolution. Idempotent.

    Read-only is not a precaution, it is a guarantee: these loaders have no business
    writing to the model, and an accidental write into a 570M-row table is not the kind
    of mistake you notice from a row count.
    """
    if con.execute("SELECT count(*) FROM duckdb_databases() WHERE database_name = ?",
                   [alias]).fetchone()[0]:
        return alias
    if not MODEL_DB.exists():
        return None
    con.execute(f"ATTACH '{MODEL_DB.as_posix()}' AS {alias} (READ_ONLY)")
    return alias


def resolve_id64(con, table, alias="model"):
    """Fill `table`.id64 by matching system against the model's name bridge.

    staging.sys_bridge is the model's precomputed (id64, system_id, sys_name) table --
    197M rows built once, because composing "<sector> <system>" on the fly over
    system_known is the single most expensive join in this project and the reason two
    earlier phantom-gap bugs happened. Probing it with a few thousand names costs one
    scan; rebuilding the name is not worth it.

    Only ever fills a NULL. A name we resolved once does not become a different system,
    and re-running must not churn rows the app is reading.

    Returns rows filled, or None when the model is unavailable -- a missing model is
    NOT an error here. The app must start and record where you flew even if the 60 GiB
    file is mid-rebuild, on another disk, or absent entirely.
    """
    if attach_model(con, alias) is None:
        return None
    # duckdb_tables() is a TABLE FUNCTION and CANNOT be database-qualified --
    # `model.duckdb_tables()` raises "Table Function with name duckdb_tables does not
    # exist". It already reports every attached database, so filter on database_name.
    # Note that is the ATTACH ALIAS, not the filename.
    if not con.execute(
            """SELECT count(*) FROM duckdb_tables()
               WHERE database_name = ? AND schema_name = 'staging'
                 AND table_name = 'sys_bridge'""", [alias]).fetchone()[0]:
        return None
    n = con.execute(f"""
        SELECT count(*) FROM {table} t
        WHERE t.id64 IS NULL
          AND EXISTS (SELECT 1 FROM {alias}.staging.sys_bridge b
                      WHERE b.sys_name = t.system)""").fetchone()[0]
    if n:
        con.execute(f"""
            UPDATE {table} AS t SET id64 = b.system_id64
            FROM {alias}.staging.sys_bridge AS b
            WHERE b.sys_name = t.system AND t.id64 IS NULL""")
    return n


def resolve_known(con, table, alias="model", only=None, recheck=False):
    """Fill `table`.is_known: is this system already in the dumps?

    The sibling of resolve_id64, against the same 197M-row name bridge, and separate
    from it for one reason: id64 has no way to say "checked, and it is NOT there". A
    NULL id64 means either "never resolved" or "no such system in any dump", and the
    Confirmed table has to tell those apart -- one is a system worth flying to and the
    other is somebody else''s discovery.

    TWO PASSES, AND THE FIRST ONE IS FREE.

      1. system_predicted.is_catalog. That table holds two populations and the flag
         separates them exactly: every one of its 2,207,261 catalogued rows resolves to
         a system_known row, and none of its 61,763 boxel rows does. So where it has an
         opinion it IS the answer -- measured against the bridge over every row we hold,
         920 agreements and 0 disagreements -- and it costs a join against 2.27M rows
         instead of a scan of 197M.

      2. staging.sys_bridge, for whatever pass 1 could not place. *** ABSENCE FROM
         system_predicted IS NOT EVIDENCE OF ANYTHING. *** Its catalogued half contains
         only dump systems NOBODY HAS DETAIL-SCANNED; a dump system that has been
         scanned never enters the table at all. Of the rare reveals we hold that are
         missing from system_predicted, 747 are in the dumps and 518 are genuinely new,
         so guessing from absence would be wrong more often than right.

    `only` is a SQL predicate narrowing which rows are worth resolving -- the caller
    knows what it will read the flag for. *** THIS IS THE DIFFERENCE BETWEEN 1,729 ms
    AND NOTHING. *** Pass 2 costs one scan of a 197M-row table with no index on the
    name, and that cost is the same whether it probes one name or ten thousand; the
    only way to make it cheap is not to run it. The overlay reads is_known solely for
    rare arrival classes, which are 1,673 of 13,671 rows, and most route plots reveal
    none at all -- so with `only` set, most plots skip both passes entirely.

    `recheck` re-examines rows already marked FALSE. A FALSE describes the dumps as they
    stood at the last model rebuild and goes stale in one direction: somebody else
    reports the system and it becomes TRUE. TRUE never reverts. Loaders pass recheck
    because they run rarely and can afford the scan; the overlay does not, because a
    stale FALSE costs one wrongly-offered target while a scan costs 1.7 s of every plot.

    Returns rows now TRUE, or None when the model is unavailable. A missing model is NOT
    an error: the app must still record where you flew.
    """
    if attach_model(con, alias) is None:
        return None
    # duckdb_tables() is a TABLE FUNCTION and cannot be database-qualified; filter on
    # database_name, which is the ATTACH alias. Same trap as resolve_id64.
    if not con.execute(
            """SELECT count(*) FROM duckdb_tables()
               WHERE database_name = ? AND schema_name = 'staging'
                 AND table_name = 'sys_bridge'""", [alias]).fetchone()[0]:
        return None
    scope = f"({only})" if only else "TRUE"
    # Unresolved means NULL; with recheck a FALSE counts as unresolved too.
    unresolved = "t.is_known IS NULL" if not recheck else "t.is_known IS NOT TRUE"

    # PASS 1 -- free, where system_predicted has an opinion.
    con.execute(f"""
        UPDATE {table} AS t SET is_known = p.is_catalog
        FROM {alias}.main.system_predicted AS p
        WHERE p.system = t.system AND {unresolved} AND {scope}""")

    # PASS 2 -- the 197M-row scan, and ONLY if something still needs it.
    left = con.execute(
        f"SELECT count(*) FROM {table} t WHERE {unresolved} AND {scope}").fetchone()[0]
    if left:
        con.execute(f"""
            UPDATE {table} AS t
            SET is_known = EXISTS (SELECT 1 FROM {alias}.staging.sys_bridge b
                                   WHERE b.sys_name = t.system)
            WHERE {unresolved} AND {scope}""")
    return con.execute(
        f"SELECT count(*) FROM {table} WHERE is_known").fetchone()[0]


# ---------------------------------------------------------------- loader plumbing
# Every app-state loader does the same four things around its own merge SQL: open the
# database, re-assert schema/<table>.sql, count before, and report after. That shape is
# here ONCE rather than copied into each loader -- a merge report that drifts between
# tables is how a no-op run stops looking like a no-op.
def begin(table):
    """Open the app-state DB and re-assert `table`'s DDL + comments. -> (con, before).

    Re-applying the schema file is free (`CREATE TABLE IF NOT EXISTS`) and cannot
    reshape anything, which is what makes it safe to do on every run -- and it is the
    only thing that keeps COMMENT ON text alive across a migration.
    """
    con = connect()
    con.execute((SCHEMA / f"{table}.sql").read_text(encoding="utf-8"))
    print(f"database: {CURRENT_DB.name}")
    return con, con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def finish(con, table, before, updated=0, resolve=True):
    """Report the merge and resolve id64. -> row count after.

    Prints the same summary shape as common.db.report_merge so an app-state load and a
    model load read alike.
    """
    after = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    print(f"\nmerged {table}: {after - before} inserted, {updated} updated, "
          f"{before} -> {after} rows")

    # Derive `sector` for anything that lacks it. Done HERE, once, rather than in each
    # loader's INSERT: every app-state table has the column, every loader calls this,
    # and one definition (sector_sql) means the column cannot come to mean different
    # things in different rows. Only ever fills a NULL -- a name does not change sector.
    n = con.execute(f"""SELECT count(*) FROM {table}
                        WHERE sector IS NULL AND system IS NOT NULL
                          AND {sector_sql('system')} IS NOT NULL""").fetchone()[0]
    if n:
        con.execute(f"""UPDATE {table} SET sector = {sector_sql('system')}
                        WHERE sector IS NULL""")
    known = con.execute(f"SELECT count(sector) FROM {table}").fetchone()[0]
    if after:
        print(f"  sector: {n:,} derived this run, {known:,}/{after:,} known "
              f"({known / after:.1%}) -- the rest are hand-named systems, which have "
              f"no procedural sector")
    # is_known only exists on the tables that feed the Confirmed table; the others
    # have no use for it and no column to put it in.
    if resolve and after and con.execute(
            "SELECT count(*) FROM duckdb_columns() WHERE table_name = ? "
            "AND column_name = 'is_known'", [table]).fetchone()[0]:
        n_known = resolve_known(con, table, recheck=True)
        if n_known is not None:
            print(f"  is_known: {n_known:,}/{after:,} already reported to the dumps "
                  f"({n_known / after:.1%}) -- those are somebody else's discovery, "
                  f"not a find")
    if resolve and after:
        filled = resolve_id64(con, table)
        if filled is None:
            print("  id64: model database unavailable -- left NULL (not an error)")
        else:
            known = con.execute(f"SELECT count(id64) FROM {table}").fetchone()[0]
            print(f"  id64: {filled:,} resolved this run, {known:,}/{after:,} known "
                  f"({known / after:.1%})")
    return after

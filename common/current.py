"""Shared plumbing for elite_mapping_v2_current.duckdb -- the APP-STATE database.

Two databases, two jobs, and keeping them apart is the point:

  elite_mapping_v2.duckdb          the MODEL. What the galaxy is, merged from Spansh,
                                   EDSM, EDAstro and Canonn. 60 GiB, rebuilt by etl/.
  elite_mapping_v2_current.duckdb  what THIS COMMANDER has done, in `main`, appended
                                   to by the overlay while you fly and never rebuilt --
                                   PLUS a `model` schema holding a mirror of the ten
                                   model tables the overlay reads (MODEL_TABLES and
                                   PROBE_TABLE below), which etl/refresh_current.py
                                   rebuilds whole and which is pure cache.

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

*** THE OVERLAY NO LONGER OPENS THE MODEL AT ALL. *** It reads the `model` schema of
this file, which removes the question rather than answering it: the app cannot write a
file it never attaches, and `etl/` can merge the 60 GiB model while the HUD is flying
because the two processes no longer touch it together. attach_model() remains for the
loaders that BUILD from the model -- etl/refresh_current.py and resolve_id64() -- and
attaches READ_ONLY, so an accidental write there raises rather than lands.

Keep the two schemas apart when adding a table. `main` RECORDS and is irreplaceable;
`model` is a cache and is dropped and rebuilt on every refresh. A table in the wrong one
is either lost on the next refresh or never updated again, and nothing will say so.

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

# WHICH TABLES BELONG TO THIS DATABASE. schema/ is one flat directory shared with the
# model, so the filename cannot say which database a table lives in -- this list is the
# only thing that does. Order is load order. Add a table here or create_current_db.py
# will not build it, and no error will tell you: an unlisted schema file is simply a
# file nobody reads.
CURRENT_TABLES = ["system_seen", "system_visited", "system_confirmed", "poi_visited",
                  "system_wrong", "route"]

# WHICH MODEL TABLES THE OVERLAY READS, and therefore what etl/refresh_current.py
# mirrors verbatim into the `model` schema of this database. Order is load order.
# Everything the app's SQL names under the model alias is here and nothing else -- 6.1M
# rows against the model's 570M, because system_known and system_body are never read.
MODEL_SCHEMA = "model"
MODEL_TABLES = ["region", "sector", "poi", "system_predicted", "system_poi",
                "carrier", "carrier_position", "system_unfound", "station_service"]

# DERIVED INTO THE MIRROR, not copied into it: {table: SELECT}. The model holds no
# corresponding table, because one would be an intermediate between two derivations --
# something to go stale rather than something to read. See etl/refresh_current.py.
DERIVED_TABLES = {
    # Systems whose ARRIVAL star is a neutron, which is what makes one supercharge-able.
    #
    # *** ARRIVAL STAR ONLY, AND IT MUST STAY THAT WAY. *** In g and h systems the
    # neutron is essentially never the arrival star, so this is emphatically NOT
    # "systems containing a neutron"; a waypoint you have to supercruise to is not a
    # waypoint. Joined on body.code, never on a body_id literal.
    # (columns, SELECT). *** THE COLUMNS ARE NAMED HERE, NOT READ OFF THE TABLE. ***
    # Reading them off the table couples this to the DDL in a way that cannot be
    # changed: dropping a column would need the SELECT changed in the same instant, and
    # a mismatch fails the refresh AFTER the drop-and-CHECKPOINT, which empties the
    # whole mirror. Naming them means the DDL may carry columns this does not fill.
    "system_neutron": (
        "system_id, sector_id, system_in_sector, cube_id, mass_code, sub_cube_id,"
        " boxel_index, region_id, primary_star_body_id, body_count, x, y, z, id_poi",
        """
        SELECT k.system_id, k.sector_id, k.system_in_sector, k.cube_id, k.mass_code,
               k.sub_cube_id, k.boxel_index, k.region_id, k.primary_star_body_id,
               k.body_count, k.x, k.y, k.z, k.id_poi
        FROM {src}.main.system_known k
        JOIN {src}.main.body b ON b.body_id = k.primary_star_body_id
                              AND b.code = 'N'"""),
}

# NOT a mirror of anything: a pruned membership set of system NAMES, built by the same
# refresh, so resolve_known() can answer is_known against 6.9M rows in THIS database
# rather than 200.8M in the model -- which is what lets the overlay answer it without
# opening the model at all. Kept out of MODEL_TABLES because it has no main.<table> to
# copy from; see its schema file.
PROBE_TABLE = "system_known_probe"


def sector_sql(name_expr):
    """SQL deriving the procedural sector from a system-name expression.

    THE ONE DEFINITION. Every app-state table stores `sector` and every writer -- the
    overlay and the rebuild script -- fills it through this, so the column cannot
    mean different things in different rows.

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


def full_name_sql(k="k", sc="sc"):
    """SQL composing a system's FULL, PASTEABLE name from a system table and `sector`.

    THE ONE DEFINITION, because a name that cannot be pasted is worse than no name and
    the mistake is invisible: the string looks plausible right up until the galaxy map
    refuses it. The overlay composes neutron and unfound names with this, and so does
    the route solver.

    *** sector_id = 0 IS THE 'crafted' SENTINEL AND ITS NAME STANDS ALONE. *** A
    hand-named system is stored with sector_id 0 -- the sector table's row 0 is
    literally named 'crafted' -- so the obvious `sc.sector || ' ' || k.system_in_sector`
    yields "crafted Charick Drift", which is not a place.

    It matters most for carriers: 2,044 of the ~2,524 reliable ones are parked in
    hand-named systems. Test by sector_id and NEVER by sector.is_crafted, which is TRUE
    for 424 real named sectors as well. Same rule as schema/system_all.sql.
    """
    return (f"CASE WHEN {k}.sector_id = 0 THEN {k}.system_in_sector "
            f"ELSE {sc}.sector || ' ' || {k}.system_in_sector END")


def mass_code_sql(name_expr):
    """SQL deriving the procedural MASS CODE from a system-name expression.

    THE ONE DEFINITION, and the twin of sector_sql() -- same name grammar, same
    anchoring, same NULL-for-hand-named behaviour. app/names.py:mass_code_of() is the
    Python twin, used where no database is in hand; the two must stay in step.

    Mass code is the size class of the generator cube -- 'a' smallest, 'h' largest --
    and the strongest single predictor the model has, which is why it is worth reading
    straight off the name rather than joining 197M rows to look it up.
    """
    return (r"nullif(regexp_extract({}, '^.* [A-Z][A-Z]-[A-Z] ([a-h])\d', 1), '')"
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
    very handle, on every jump -- so the settings below are sized for those, not for
    the app-state tables. threads=4 on a 16-core machine measures 87 ms against 46 ms
    for the same neutron query; eight is a deliberate middle, because the queries are
    short bursts and the machine is also running a game.
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
    """Fill `table`.id64 by matching system name against the model. -> rows filled.

    Matches on the name composed through full_name_sql(), which is the one definition
    of that rule. A scan of system_known either way -- the name is computed, so nothing
    can index it -- and 2.76 s over the 16,636 names a load actually probes.

    *** AN AMBIGUOUS NAME IS LEFT UNRESOLVED, DELIBERATELY. *** 1,477 composed names
    belong to more than one system: 3,349 rows, nearly all catalogue designations like
    "2MASS J03285461+3116512", and NGC 2168 SB 746 is five different stars. Composing
    the sector back on is what merges them -- the full name is a WEAKER key than the
    (sector_id, system_in_sector) pair it is built from, which collides only 49 times.
    Resolving one of them means writing a coin flip into the database that cannot be
    rebuilt, so `HAVING count(*) = 1` drops them and they stay NULL. Nothing in this
    commander's tables has hit one yet.

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
               WHERE database_name = ? AND schema_name = 'main'
                 AND table_name = 'system_known'""", [alias]).fetchone()[0]:
        return None
    # One name to one id64, or nothing. HAVING count(*) = 1 is what drops the ambiguous
    # ones; min() would resolve them to whichever star sorted first.
    named = f"""
        SELECT {full_name_sql('k', 'sc')} AS sys_name, min(k.system_id) AS system_id64
        FROM {alias}.main.system_known k
        JOIN {alias}.main.sector sc ON sc.sector_id = k.sector_id
        WHERE {full_name_sql('k', 'sc')} IN (SELECT system FROM {table}
                                             WHERE id64 IS NULL)
        GROUP BY 1 HAVING count(*) = 1"""
    con.execute(f"CREATE OR REPLACE TEMP TABLE _id64_of AS {named}")
    n = con.execute(f"""
        SELECT count(*) FROM {table} t
        WHERE t.id64 IS NULL
          AND EXISTS (SELECT 1 FROM _id64_of b WHERE b.sys_name = t.system)"""
                    ).fetchone()[0]
    if n:
        con.execute(f"""
            UPDATE {table} AS t SET id64 = b.system_id64
            FROM _id64_of AS b
            WHERE b.sys_name = t.system AND t.id64 IS NULL""")
    con.execute("DROP TABLE IF EXISTS _id64_of")
    return n


def resolve_known(con, table, only=None, recheck=False):
    """Fill `table`.is_known: is this system already in the dumps?

    Reads the MIRROR IN THIS DATABASE and attaches nothing. Both tables it needs --
    model.system_predicted and model.system_known_probe -- are put there by
    etl/refresh_current.py, so the 60 GiB model is not involved and the overlay can
    answer this while a merge is halfway through rewriting it.

    The sibling of resolve_id64, and separate from it for one reason: id64 has no way
    to say "checked, and it is NOT there". A NULL id64 means either "never resolved" or
    "no such system in any dump", and the Confirmed table has to tell those apart --
    one is a system worth flying to and the other is somebody else's discovery.

    TWO PASSES, AND THEY DIFFER IN WHAT THEY CAN PROVE.

      1. system_predicted.is_catalog, which is EXACT IN BOTH DIRECTIONS. That table
         holds two populations and the flag separates them: its catalogued rows all
         resolve to a system_known row and its boxel rows never do. So where it has an
         opinion it IS the answer -- 920 agreements and 0 disagreements against the
         full name bridge over every row we hold -- and it writes TRUE and FALSE alike.
         *** ABSENCE FROM IT IS NOT EVIDENCE OF ANYTHING ***: its catalogued half holds
         only dump systems nobody has detail-scanned, so a scanned one never enters.

      2. system_known_probe, for whatever pass 1 could not place. *** ONE-SIDED: A HIT
         IS PROOF AND A MISS IS NOT, SO THIS PASS ONLY EVER WRITES TRUE. *** The probe
         is pruned by mass code and drops systems the dumps positively rule out, which
         is what makes it 76 MB instead of 2.33 GB; the price is that it misses the
         neutrons and white dwarfs the Forge builds below its floor. Writing FALSE here
         would turn "we did not find it" into "nobody has reported it", which is a
         claim this table cannot make. A miss stays NULL, and NULL already means "show
         it" everywhere is_known is read.

    `only` is a SQL predicate narrowing which rows are worth resolving. It no longer
    buys much -- the probe is ~300 ms cold and 3 ms warm, against the 1,729 ms scan
    that made the argument necessary -- but the overlay reads is_known solely for rare
    arrival classes, so passing it still skips both passes on most route plots.

    `recheck` re-examines rows already marked FALSE. A FALSE describes the dumps as
    they stood at the last refresh and goes stale in one direction: somebody else
    reports the system and it becomes TRUE. TRUE never reverts.

    Returns rows now TRUE, or None when the mirror is absent -- which is NOT an error.
    The app must start and record where you flew even if nothing has built the mirror
    yet; run etl/refresh_current.py to fill it.
    """
    have = {r[0] for r in con.execute(
        """SELECT table_name FROM duckdb_tables() WHERE schema_name = ?""",
        [MODEL_SCHEMA]).fetchall()}
    if "system_predicted" not in have and PROBE_TABLE not in have:
        return None
    scope = f"({only})" if only else "TRUE"
    # Unresolved means NULL; with recheck a FALSE counts as unresolved too.
    unresolved = "t.is_known IS NULL" if not recheck else "t.is_known IS NOT TRUE"

    # PASS 1 -- exact both ways, where system_predicted has an opinion.
    if "system_predicted" in have:
        con.execute(f"""
            UPDATE {table} AS t SET is_known = p.is_catalog
            FROM {MODEL_SCHEMA}.system_predicted AS p
            WHERE p.system = t.system AND {unresolved} AND {scope}""")

    # PASS 2 -- TRUE only, and ONLY if something still needs it.
    if PROBE_TABLE in have and con.execute(
            f"SELECT count(*) FROM {table} t "
            f"WHERE {unresolved} AND {scope}").fetchone()[0]:
        con.execute(f"""
            UPDATE {table} AS t SET is_known = TRUE
            WHERE {unresolved} AND {scope}
              AND EXISTS (SELECT 1 FROM {MODEL_SCHEMA}.{PROBE_TABLE} b
                          WHERE b.system = t.system)""")
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

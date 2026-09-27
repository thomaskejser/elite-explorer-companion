import re
import sys, pathlib, time

import duckdb

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common.db import apply_comment_file, comment_file, connect, table_count

import importlib
sk_load = importlib.import_module("etl.system_known.load")

MAP = "staging.rekey"
# Everything here runs bucketed, and the key is now an index built once at the end
# rather than a PRIMARY KEY maintained row by row, so nothing has to stay resident
# across the load. The declared-key version needed more than 13 GiB and still died.
MEMORY = "8GB"

DEPENDENTS = {
    "carrier_position": None,
    "carrier": "system_id",
    "system_catalog": "system_id",
    "system_phenomenon": "system_id",
    "system_neutron": "system_id",
    "system_poi": "system_id",
    "system_body": "system_id",
}

DEDUPE = {
    "system_neutron": ["system_id"],
    "system_poi": ["system_id", "poi_id"],
}

INSERT_BUCKETS = {"system_body": ("system_body_id", 32)}
DONE = "staging.rekey_done"


def step(n, what):
    print(f"\n{'='*78}\nPHASE {n}  {what}\n{'='*78}", flush=True)


def build_map(con):
    step(1, "old system_id -> id64")
    if con.execute(f"""SELECT count(*) FROM duckdb_tables()
                       WHERE schema_name='staging' AND table_name='rekey'""").fetchone()[0]:
        n, distinct = con.execute(f"""SELECT count(*), count(DISTINCT system_id)
                                      FROM {MAP}""").fetchone()
        print(f"  reusing {MAP}: {n:,} old ids -> {distinct:,} distinct new ids")
        return n
    con.execute(f"""CREATE OR REPLACE TABLE {MAP} AS
        SELECT k.system_id AS old_system_id,
               coalesce(k.id64,
                        system_id_from_name(CASE WHEN k.sector_id = 0
                                                 THEN k.system_in_sector
                                                 ELSE s.sector || ' ' || k.system_in_sector
                                            END)) AS system_id
        FROM main.system_known k
        LEFT JOIN main.sector s ON s.sector_id = k.sector_id""")
    n, distinct, null_id64 = con.execute(f"""
        SELECT count(*), count(DISTINCT system_id), count(*) FILTER (WHERE system_id IS NULL)
        FROM {MAP}""").fetchone()
    print(f"  {n:,} old ids -> {distinct:,} distinct new ids "
          f"({n - distinct:,} collapse, the duplicate-spelling rows)")
    if null_id64:
        raise SystemExit(f"{null_id64:,} rows resolve to no id at all -- refusing")
    return n


def build_transform(con):
    step(2, "transform.system_known from the staged catalogues")
    if con.execute("""SELECT count(*) FROM duckdb_tables() WHERE schema_name='transform'
                      AND table_name='system_known'""").fetchone()[0] and        table_count(con, "transform.system_known") > 100_000_000:
        n = table_count(con, "transform.system_known")
        print(f"  reusing transform.system_known: {n:,} row(s) already shaped")
        return n
    t0 = time.time()
    n = sk_load.build_transform(con)
    print(f"  {n:,} row(s) from the dumps in {time.time()-t0:.0f}s")

    print("  carrying across systems no staged dump holds...", flush=True)
    con.execute(f"""INSERT INTO transform.system_known
        SELECT DISTINCT ON (m.system_id)
               m.system_id, k.sector_id, k.system_in_sector, k.cube_id, k.mass_code,
               k.sub_cube_id, k.boxel_index, k.region_id, k.primary_star_body_id,
               k.body_count, k.x, k.y, k.z, 'model' AS source
        FROM main.system_known k
        JOIN {MAP} m ON m.old_system_id = k.system_id
        WHERE k.x IS NOT NULL AND k.y IS NOT NULL AND k.z IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM transform.system_known t
                          WHERE t.system_id = m.system_id)
        ORDER BY m.system_id, k.system_id""")
    carried = table_count(con, "transform.system_known") - n
    print(f"  {carried:,} carried across, {table_count(con, 'transform.system_known'):,} total")
    sk_load.fill_region(con)
    return table_count(con, "transform.system_known")


def rebuild(con, table, column):
    """Copy a table aside, drop it, recreate it from schema/ (which declares no FOREIGN
    KEY), and put the rows back with system_id re-keyed.

    Resumable, because it is the destructive half: a table already recorded in
    staging.rekey_done is skipped, and one whose rows are still sitting in
    staging.mig_<table> after a failure is finished from there rather than re-derived.
    """
    con.execute(f"CREATE TABLE IF NOT EXISTS {DONE} (table_name VARCHAR)")
    if con.execute(f"SELECT count(*) FROM {DONE} WHERE table_name = ?",
                   [table]).fetchone()[0]:
        print(f"  {table:<20}already re-keyed, skipped")
        return

    mig = f"staging.mig_{table}"
    have_mig = con.execute("""SELECT count(*) FROM duckdb_tables()
                              WHERE schema_name='staging' AND table_name = ?""",
                           [f"mig_{table}"]).fetchone()[0]
    before = table_count(con, f"main.{table}")

    if not have_mig:
        cols = [r[0] for r in con.execute(f"DESCRIBE main.{table}").fetchall()]
        if column:
            select = ", ".join(f"m.system_id AS {c}" if c == column else f"t.{c}"
                               for c in cols)
            join = "LEFT JOIN" if _nullable_zero(con, table, column) else "JOIN"
            src = f"FROM main.{table} t {join} {MAP} m ON m.old_system_id = t.{column}"
        else:
            select = ", ".join(f"t.{c}" for c in cols)
            src = f"FROM main.{table} t"
        con.execute(f"CREATE OR REPLACE TABLE {mig} AS SELECT {select} {src}")
        con.execute(f"DROP TABLE IF EXISTS main.{table}")
        apply_comment_file(con, comment_file(table))
    else:
        print(f"  {table:<20}resuming from {mig}")
        if before:
            con.execute(f"DROP TABLE main.{table}")
            apply_comment_file(con, comment_file(table))
            before = 0

    kept = table_count(con, mig)
    keys = DEDUPE.get(table)
    k = ", ".join(keys) if keys else None
    bucket = INSERT_BUCKETS.get(table)
    if bucket:
        col, n = bucket
        for b in range(n):
            con.execute(f"INSERT INTO main.{table} SELECT * FROM {mig} "
                        f"WHERE hash({col}) % {n} = {b}")
    elif keys:
        con.execute(f"INSERT INTO main.{table} "
                    f"SELECT DISTINCT ON ({k}) * FROM {mig} ORDER BY {k}")
    else:
        con.execute(f"INSERT INTO main.{table} SELECT * FROM {mig}")
    con.execute(f"DROP TABLE {mig}")
    con.execute(f"INSERT INTO {DONE} VALUES (?)", [table])

    after = table_count(con, f"main.{table}")
    collapsed = kept - after
    note = (f"   {collapsed:,} row(s) collapsed onto a merged system_id"
            if collapsed and keys else
            f"   <== {collapsed:,} LOST ON INSERT" if collapsed else "")
    print(f"  {table:<20}{kept:>14,} -> {after:>14,}{note}", flush=True)


def _nullable_zero(con, table, column):
    return con.execute(f"SELECT count(*) FILTER (WHERE {column} IS NULL) > 0 "
                       f"FROM main.{table}").fetchone()[0]


def rebuild_dependents(con):
    step(3, "re-keying every table that carries system_id, and dropping its FOREIGN KEYs")
    for table, column in DEPENDENTS.items():
        t0 = time.time()
        rebuild(con, table, column)
        print(f"    {time.time()-t0:.0f}s", flush=True)


def retire(con, table):
    """Get rid of the pre-re-key table, or empty it when the catalog will not let go.

    This database carries catalog entries for tables that no longer appear in
    duckdb_tables() -- `system_catalog_new`, left by an old create-copy-swap. DuckDB
    still honours their foreign keys, so a DROP of anything they reference fails with
    `this table is main key table of the table "X"` naming an X you cannot see; CASCADE
    does not help and `DROP TABLE IF EXISTS X` silently no-ops because the name does not
    resolve. TRUNCATE releases the rows even when the shell cannot go.
    """
    try:
        con.execute(f"DROP TABLE main.{table}")
        print(f"  dropped main.{table}")
    except Exception as exc:                                           # noqa: BLE001
        con.execute(f"TRUNCATE main.{table}")
        print(f"  main.{table} cannot be dropped -- {str(exc).splitlines()[0][:90]}")
        print(f"  TRUNCATED instead: the rows are gone, an empty shell remains and it "
              f"goes on the next fresh build")


def rebuild_system_known(con):
    step(4, "rebuilding main.system_known on the new key")
    old = "system_known_pre_rekey"
    if con.execute("""SELECT count(*) FROM duckdb_tables()
                      WHERE schema_name='main' AND table_name = ?""",
                   [old]).fetchone()[0]:
        print(f"  resuming: main.{old} is already aside and main.system_known is "
              f"re-created; the merge is idempotent so it restarts from bucket 0")
    else:
        con.execute(f"ALTER TABLE main.system_known RENAME TO {old}")
    apply_comment_file(con, comment_file("system_known"))
    print("  recreated from schema/system_known.sql: "
          f"{[r[0] for r in con.execute('DESCRIBE main.system_known').fetchall()]}")
    sk_load.load(con, shape=False)
    retire(con, old)


def verify(con):
    step(5, "verification")
    print(con.execute("""
        SELECT count(*) AS systems,
               count(*) FILTER (WHERE system_id < 0) AS ours,
               count(*) FILTER (WHERE region_id IS NULL) AS no_region,
               count(*) FILTER (WHERE sector_id = 0) AS hand_named,
               min(first_seen) AS first_seen
        FROM main.system_known""").fetchdf().to_string(index=False))
    print()
    for table, column in DEPENDENTS.items():
        if not column:
            continue
        n = con.execute(f"""SELECT count(*) FROM main.{table} t
                            WHERE t.{column} IS NOT NULL
                              AND NOT EXISTS (SELECT 1 FROM main.system_known k
                                              WHERE k.system_id = t.{column})""").fetchone()[0]
        print(f"  {table}.{column} -> system_known.system_id: {n:,}"
              + ("   <== DANGLING" if n else ""))
    print()
    print(con.execute("""SELECT table_name, constraint_type FROM duckdb_constraints()
        WHERE schema_name='main' AND constraint_type='FOREIGN KEY'""")
        .fetchdf().to_string(index=False) or "  no FOREIGN KEY left in main")


def main():
    con = connect(memory_limit=MEMORY, threads=6)
    try:
        build_map(con)
        build_transform(con)
        rebuild_dependents(con)
        rebuild_system_known(con)
        verify(con)
    finally:
        con.close()
    print("\nDONE_REKEY_TO_ID64")


if __name__ == "__main__":
    main()

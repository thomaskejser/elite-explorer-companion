import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (check_references, connect, merge_counts, prepare_table,
                       report_merge, run_sql_file, staged_source, table_count,
                       transform_file)

HERE = pathlib.Path(__file__).resolve().parent
TABLE = "sector"
STAGED = "staging.edastro_sector"
SENTINEL = "crafted"
ROLES = ("spansh_system", "edsm_star_system", "edastro_star_system")


def add_named(con):
    missing = [r for r in ROLES if not staged_source(con, r)]
    if missing:
        print(f"  sectors from staged system names NOT added: {', '.join(missing)} not staged "
              f"-- run etl/system_known/stage.py first")
        return
    named = [r[0] for r in run_sql_file(con, HERE / "named.sql").fetchall()]
    print(f"  {len(named)} sector(s) named by staged systems but absent from EDAstro's list, "
          f"added: " + ", ".join(sorted(named)[:30]) + (" ..." if len(named) > 30 else ""))


def fill_region(con):
    has_map = con.execute("""SELECT count(*) FROM information_schema.tables
                             WHERE table_schema = 'main' AND table_name = 'region_map'""").fetchone()[0]
    if not has_map:
        print("  sector regions NOT filled: there is no main.region_map -- run etl/region_map/refresh.py first")
        return 0
    if not staged_source(con, "edastro_star_system"):
        print("  sector regions NOT filled: edastro_star_system is not staged -- run etl/system_known/stage.py first")
        return 0
    filled = run_sql_file(con, HERE / "region.sql").fetchall()
    left = con.execute(f"SELECT count(*) FROM {TABLE} WHERE region_id IS NULL AND sector_id <> 0").fetchone()[0]
    print(f"  {len(filled):,} sector region(s) filled, by the modal EDAstro label of their systems "
          f"or else the region grid at the sector centre; "
          f"{left:,} lie in no region")
    return len(filled)


def load(con):
    before = prepare_table(con, TABLE, STAGED)

    run_sql_file(con, transform_file(TABLE))
    add_named(con)
    print(f"transform.sector: {table_count(con, 'transform.sector'):,} row(s)")

    inserted, updated = merge_counts(con, HERE / "counts.sql")
    run_sql_file(con, HERE / "load.sql")

    sentinel = con.execute(f"""
        INSERT INTO {TABLE} (sector_id, sector, x, y, z, radius, is_crafted)
        SELECT 0, '{SENTINEL}', 0, 0, 0, 0, true
        WHERE NOT EXISTS (SELECT 1 FROM {TABLE} WHERE sector_id = 0)
        RETURNING sector_id""").fetchall()
    if sentinel:
        print(f"  INSERT sentinel sector_id=0 '{SENTINEL}' (systems with no sector)")

    filled = fill_region(con)

    orphans = run_sql_file(con, HERE / "orphans.sql").fetchall()
    after = table_count(con, TABLE)
    report_merge(TABLE, before, after, inserted + len(sentinel), updated + filled, orphans)

    collisions = run_sql_file(con, HERE / "collisions.sql").fetchall()
    if collisions:
        print(f"\n  *** {len(collisions)} new sector(s) NOT inserted: their published id is "
              f"already held by another sector. Resolve by hand:")
        for name, sid, holder in collisions:
            print(f"    {name:<32}{sid:>14}  held by {holder}")

    drift = run_sql_file(con, HERE / "drift.sql").fetchall()
    print(f"\n  {len(drift)} sector(s) where the id EDAstro publishes differs from the one "
          f"stored; the stored id stands, because sector_id is never renumbered:")
    for name, sid, published in drift[:10]:
        print(f"    {name:<32}{sid:>14}{published:>14}")

    print("\nreferential integrity:")
    check_references(con, TABLE)

    kinds = con.execute(f"""
        SELECT is_crafted, count(*), round(avg(radius), 1)
        FROM {TABLE} WHERE sector_id <> 0 GROUP BY 1 ORDER BY 1""").fetchall()
    print(f"\n  {'sector kind':<20}{'sectors':>9}{'mean radius':>13}")
    for crafted, n, r in kinds:
        print(f"  {'hand-authored' if crafted else 'procedural':<20}{n:>9,}{r:>13.1f}")
    return after


def main():
    con = connect()
    try:
        load(con)
    finally:
        con.close()
    print("DONE_LOAD_SECTOR")


if __name__ == "__main__":
    from common.runlog import start
    start()
    main()

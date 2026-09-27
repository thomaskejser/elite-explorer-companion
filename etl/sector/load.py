import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (check_references, connect, merge_counts, prepare_table,
                       report_merge, run_sql_file, table_count, transform_file)

HERE = pathlib.Path(__file__).resolve().parent
TABLE = "sector"
STAGED = "staging.edastro_sector"
SENTINEL = "crafted"


def load(con):
    before = prepare_table(con, TABLE, STAGED)

    run_sql_file(con, transform_file(TABLE))
    n_src = table_count(con, "transform.sector")
    print(f"transform.sector: {n_src:,} row(s)")

    inserted, updated = merge_counts(con, HERE / "counts.sql")
    run_sql_file(con, HERE / "load.sql")

    sentinel = con.execute(f"""
        INSERT INTO {TABLE} (sector_id, sector, x, y, z, radius, is_crafted)
        SELECT 0, '{SENTINEL}', 0, 0, 0, 0, true
        WHERE NOT EXISTS (SELECT 1 FROM {TABLE} WHERE sector_id = 0)
        RETURNING sector_id""").fetchall()
    if sentinel:
        print(f"  INSERT sentinel sector_id=0 '{SENTINEL}' (systems with no sector)")

    orphans = run_sql_file(con, HERE / "orphans.sql").fetchall()
    after = table_count(con, TABLE)
    report_merge(TABLE, before, after, inserted + len(sentinel), updated, orphans)

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
    main()

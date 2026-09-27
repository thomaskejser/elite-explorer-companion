import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (check_references, connect, merge_counts, prepare_table,
                       report_merge, run_sql_file, table_count, transform_file)

HERE = pathlib.Path(__file__).resolve().parent
TABLE = "carrier_position"
SOURCE = "main.carrier + main.system_known"


def load(con):
    before = prepare_table(con, TABLE, SOURCE)

    run_sql_file(con, transform_file(TABLE))
    n_src, n_carrier, n_reliable, n_located = con.execute("""
        SELECT (SELECT count(*) FROM transform.carrier_position),
               (SELECT count(*) FROM main.carrier),
               (SELECT count(*) FROM main.carrier WHERE is_reliable),
               (SELECT count(*) FROM transform.carrier_position WHERE x IS NOT NULL)
        """).fetchone()
    print(f"transform.carrier_position: {n_src:,} of {n_carrier:,} carrier(s) resolve "
          f"to a system ({n_located:,} with coordinates)")
    print(f"  {n_reliable:,} are RELIABLE, which is the only pool the overlay offers")

    inserted, updated = merge_counts(con, HERE / "counts.sql")
    run_sql_file(con, HERE / "load.sql")

    orphans = [f"{r[0]}  {r[1]}"
               for r in run_sql_file(con, HERE / "orphans.sql").fetchall()[:20]]
    after = table_count(con, TABLE)
    report_merge(TABLE, before, after, inserted, updated, orphans)

    print("\nreferential integrity:")
    check_references(con, TABLE)

    missing = con.execute(f"""
        SELECT count(*) FROM main.carrier c
        WHERE c.is_reliable
          AND NOT EXISTS (SELECT 1 FROM {TABLE} p WHERE p.callsign = c.callsign)
        """).fetchone()[0]
    print(f"\n  reliable carriers with no position at all: {missing:,} -- these cannot "
          f"be ranked by distance and never appear in a 'nearest' list")
    return after


def main():
    con = connect()
    try:
        load(con)
    finally:
        con.close()
    print("DONE_LOAD_CARRIER_POSITION")


if __name__ == "__main__":
    main()

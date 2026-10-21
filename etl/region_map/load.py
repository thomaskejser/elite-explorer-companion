import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (check_references, connect, merge_counts, prepare_table, report_merge,
                       run_sql_file, table_count, transform_file)

HERE = pathlib.Path(__file__).resolve().parent
TABLE = "region_map"
STAGED = "staging.klightspeed_region_map"


def load(con):
    before = prepare_table(con, TABLE, STAGED)
    run_sql_file(con, transform_file(TABLE))
    n_src = table_count(con, f"transform.{TABLE}")
    regions = con.execute(f"SELECT count(DISTINCT region_id) FROM transform.{TABLE}").fetchone()[0]
    print(f"transform.{TABLE}: {n_src:,} run(s) in {regions} region(s)")
    unmatched = [r[0] for r in run_sql_file(con, HERE / "unmatched.sql").fetchall()]
    if unmatched:
        print(f"  ! {len(unmatched)} source region name(s) match no main.region row and were dropped: "
              + ", ".join(unmatched))

    inserted, updated = merge_counts(con, HERE / "counts.sql")
    run_sql_file(con, HERE / "load.sql")
    report_merge(TABLE, before, table_count(con, TABLE), inserted, updated, [])

    stale = run_sql_file(con, HERE / "stale.sql").fetchone()[0]
    if stale:
        run_sql_file(con, HERE / "delete.sql")
        print(f"  DELETED {stale:,} run(s) the source no longer has -- left in place they would "
              f"overlap the runs that replaced them.")
    print("\n  references:")
    check_references(con, TABLE)
    return table_count(con, TABLE)


def main():
    con = connect()
    try:
        load(con)
    finally:
        con.close()
    print("DONE_LOAD_REGION_MAP")


if __name__ == "__main__":
    from common.runlog import start
    start()
    main()

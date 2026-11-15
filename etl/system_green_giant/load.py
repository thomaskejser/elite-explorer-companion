import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (connect, merge_counts, prepare_table, report_merge,
                       run_sql_file, table_count, transform_file)

HERE = pathlib.Path(__file__).resolve().parent
TABLE = "system_green_giant"


def load(con):
    before = prepare_table(con, TABLE, "staging.spansh_galaxy_body + main.system_known")
    print("\npredicting green gas giants from every scanned gas giant...", flush=True)
    run_sql_file(con, transform_file(TABLE))
    for verdict, n in con.execute("""SELECT verdict, count(*) FROM transform.system_green_giant
                                      GROUP BY 1 ORDER BY 1""").fetchall():
        print(f"  {verdict:<22}{n:>10,} bodies")

    inserted, updated = merge_counts(con, HERE / "counts.sql")
    run_sql_file(con, HERE / "load.sql")
    merged = table_count(con, TABLE)
    report_merge(TABLE, before, merged, inserted, updated, [])

    stale = run_sql_file(con, HERE / "orphans.sql").fetchone()[0]
    if stale:
        run_sql_file(con, HERE / "delete.sql")
        print(f"\n  DELETED {stale:,} body(ies) the transform no longer calls green. "
              f"This table deliberately deletes; see ETL.md.")
    after = table_count(con, TABLE)
    print(f"  {merged:,} -> {after:,} rows after the delete")
    return after


def main():
    con = connect()
    try:
        load(con)
    finally:
        con.close()
    print("DONE_LOAD_SYSTEM_GREEN_GIANT")


if __name__ == "__main__":
    from common.runlog import start
    start()
    main()

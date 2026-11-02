import sys, pathlib, importlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (connect, merge_counts, prepare_table, report_merge,
                       run_sql_file, table_count, transform_file)

HERE = pathlib.Path(__file__).resolve().parent
TABLE = "system_exobio"
odds = importlib.import_module("etl.exobio_odds.load")


def load(con):
    before = prepare_table(con, TABLE, "transform.exobio_body + main.exobio_odds")
    if not table_count(con, "exobio_odds"):
        sys.exit("main.exobio_odds is empty -- run python etl/exobio_odds/refresh.py")
    odds.build_bodies(con)

    print("\nvaluing candidate bodies and rolling them up per system...", flush=True)
    run_sql_file(con, transform_file(TABLE))
    for label, lo, hi in (("10-20M", 10e6, 20e6), ("20-50M", 20e6, 50e6),
                          ("50-100M", 50e6, 100e6), ("100M+", 100e6, 1e18)):
        n = con.execute("""SELECT count(*) FROM transform.system_exobio
                           WHERE cr_expected >= ? AND cr_expected < ?""", [lo, hi]).fetchone()[0]
        print(f"  {label:<10}{n:>12,} systems")

    inserted, updated = merge_counts(con, HERE / "counts.sql")
    run_sql_file(con, HERE / "load.sql")
    merged = table_count(con, TABLE)
    report_merge(TABLE, before, merged, inserted, updated, [])

    stale = run_sql_file(con, HERE / "orphans.sql").fetchone()[0]
    if stale:
        run_sql_file(con, HERE / "delete.sql")
        print(f"\n  DELETED {stale:,} system(s) the transform no longer produces -- mapped, "
              f"codexed or fallen below the floor. This table deliberately deletes; see ETL.md.")
    after = table_count(con, TABLE)
    print(f"  {merged:,} -> {after:,} rows after the delete")
    return after


def main():
    con = connect(memory_limit="10GB")
    try:
        load(con)
    finally:
        con.close()
    print("DONE_LOAD_SYSTEM_EXOBIO")


if __name__ == "__main__":
    from common.runlog import start
    start()
    main()

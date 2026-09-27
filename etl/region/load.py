import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (connect, merge_counts, prepare_table, report_merge,
                       run_sql_file, table_count, transform_file)

HERE = pathlib.Path(__file__).resolve().parent
TABLE = "region"
STAGED = "staging.canonn_codex_event"
EXPECTED = 42


def load(con):
    before = prepare_table(con, TABLE, STAGED)

    run_sql_file(con, transform_file(TABLE))
    n_src = table_count(con, "transform.region")
    print(f"transform.region: {n_src} row(s)")
    if n_src != EXPECTED:
        print(f"  ! expected {EXPECTED} hand-drawn regions, got {n_src} -- "
              f"check before trusting this")

    inserted, updated = merge_counts(con, HERE / "counts.sql")
    run_sql_file(con, HERE / "load.sql")

    orphans = run_sql_file(con, HERE / "orphans.sql").fetchall()
    after = table_count(con, TABLE)
    report_merge(TABLE, before, after, inserted, updated, orphans)
    return after


def main():
    con = connect()
    try:
        load(con)
    finally:
        con.close()
    print("DONE_LOAD_REGION")


if __name__ == "__main__":
    main()

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (connect, merge_counts, prepare_table, report_merge,
                       run_sql_file, table_count, transform_file)

HERE = pathlib.Path(__file__).resolve().parent
TABLE = "body"
CENSUS = "spansh_galaxy_body"


def load(con):
    before = prepare_table(con, TABLE, "staging.body_curated + staging." + CENSUS)

    run_sql_file(con, transform_file(TABLE))
    print(f"transform.body: {table_count(con, 'transform.body'):,} row(s)")

    inserted, updated = merge_counts(con, HERE / "counts.sql")
    run_sql_file(con, HERE / "load.sql")

    orphans = [f"body_id={r[0]:<4} {r[1]}/{r[2]}"
               for r in run_sql_file(con, HERE / "orphans.sql").fetchall()]
    after = table_count(con, TABLE)
    report_merge(TABLE, before, after, inserted, updated, orphans)

    if con.execute("""SELECT count(*) FROM duckdb_tables()
                       WHERE schema_name = 'staging' AND table_name = ?""",
                   [CENSUS]).fetchone()[0]:
        recounted = run_sql_file(con, HERE / "census.sql").fetchone()[0]
        print(f"  observed/bodies recounted from staging.{CENSUS}: {recounted} type(s) changed")
    else:
        print(f"  *** staging.{CENSUS} IS MISSING: observed/bodies not recounted, "
              f"so a new type holds 0 ***\n"
              f"  They count the FULL Spansh catalogue; stage it with:\n"
              f"    python etl/system_known/stage.py --window full")

    unvalued, unobserved = con.execute(f"""
        SELECT count(*) FILTER (WHERE cr_value IS NULL OR value_formula IS NULL),
               count(*) FILTER (WHERE NOT observed)
        FROM {TABLE}""").fetchone()
    print(f"  types lacking a scan-value constant: {unvalued}"
          + ("   <== every one of these values as 0" if unvalued else ""))
    print(f"  types absent from the Spansh catalogue: {unobserved}")
    return after


def main():
    con = connect()
    try:
        load(con)
    finally:
        con.close()
    print("DONE_LOAD_BODY")


if __name__ == "__main__":
    from common.runlog import start
    start()
    main()

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (connect, merge_counts, prepare_table, report_merge,
                       run_sql_file, table_count, transform_file)

HERE = pathlib.Path(__file__).resolve().parent
TABLE = "body"
CENSUS = "spansh_galaxy_body"


def load(con):
    if not con.execute("""SELECT count(*) FROM duckdb_tables()
                          WHERE schema_name = 'staging' AND table_name = ?""",
                       [CENSUS]).fetchone()[0]:
        sys.exit(f"staging.{CENSUS} is missing -- the observed/bodies census is counted "
                 f"from the FULL Spansh catalogue. Stage it with:\n"
                 f"    python etl/system_known/refresh.py --window full")
    before = prepare_table(con, TABLE, "staging.body_curated + staging." + CENSUS)

    run_sql_file(con, transform_file(TABLE))
    print(f"transform.body: {table_count(con, 'transform.body'):,} row(s)")

    inserted, updated = merge_counts(con, HERE / "counts.sql")
    run_sql_file(con, HERE / "load.sql")

    orphans = [f"body_id={r[0]:<4} {r[1]}/{r[2]}"
               for r in run_sql_file(con, HERE / "orphans.sql").fetchall()]
    after = table_count(con, TABLE)
    report_merge(TABLE, before, after, inserted, updated, orphans)

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
    main()

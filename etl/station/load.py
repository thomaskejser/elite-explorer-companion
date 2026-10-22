import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (connect, merge_counts, prepare_table, report_merge, run_sql_file,
                       table_count, transform_file)

HERE = pathlib.Path(__file__).resolve().parent
TABLE = "station"
STAGED = "staging.spansh_galaxy_station"
SERVICES = (("Universal Cartographics", "has_universal_cartographics"),
            ("Vista Genomics", "has_vista_genomics"),
            ("Large pad, repair and rearm", "has_repair AND has_restock AND coalesce(large_pads, 0) > 0"))


def load(con):
    before = prepare_table(con, TABLE, STAGED)
    run_sql_file(con, transform_file(TABLE))
    print(f"transform.{TABLE}: {table_count(con, f'transform.{TABLE}'):,} of "
          f"{table_count(con, STAGED):,} staged station(s) offer one of the three")
    inserted, updated = merge_counts(con, HERE / "counts.sql")
    run_sql_file(con, HERE / "load.sql")
    report_merge(TABLE, before, table_count(con, TABLE), inserted, updated, [])

    print(f"\n  {'service':<30}{'stations':>10}{'carriers':>10}{'carriers, 7 days':>18}")
    for label, where in SERVICES:
        n, c, recent = con.execute(f"""
            SELECT count(*) FILTER (WHERE NOT is_carrier), count(*) FILTER (WHERE is_carrier),
                   count(*) FILTER (WHERE is_carrier AND last_reported >= now() - INTERVAL 7 DAY)
            FROM {TABLE} WHERE is_listed AND {where}""").fetchone()
        print(f"  {label:<30}{n:>10,}{c:>10,}{recent:>18,}")
    return table_count(con, TABLE)


def main():
    con = connect(memory_limit="8GB", threads=8)
    try:
        load(con)
    finally:
        con.close()
    print("DONE_LOAD_STATION")


if __name__ == "__main__":
    from common.runlog import start
    start()
    main()

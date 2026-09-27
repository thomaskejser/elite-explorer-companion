import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (connect, merge_counts, prepare_table, report_merge,
                       run_sql_file, table_count, transform_file)

HERE = pathlib.Path(__file__).resolve().parent
TABLE = "system_catalog_alias"
STAGED = "staging.system_catalog_alias_curated"


def load(con):
    before = prepare_table(con, TABLE, STAGED)

    run_sql_file(con, transform_file(TABLE))
    print(f"transform.{TABLE}: {table_count(con, f'transform.{TABLE}'):,} identities")

    inserted, updated = merge_counts(con, HERE / "counts.sql")
    run_sql_file(con, HERE / "load.sql")
    report_merge(TABLE, before, table_count(con, TABLE), inserted, updated, [])

    retracted = run_sql_file(con, HERE / "retracted.sql").fetchall()
    if retracted:
        run_sql_file(con, HERE / "delete.sql")
        print(f"  DELETED {sum(n for _, n in retracted):,} identity(ies) the file does "
              f"not assert:")
        for source, n in retracted:
            print(f"    {source:<18}{n:>10,}")
        print("  *** re-run etl/system_catalog/refresh.py -- it recomputes every "
              "alias-resolved system_id, and drops the ones these edges justified.")

    print("\n  identities by source:")
    for source, n in con.execute(f"""SELECT source, count(*) FROM {TABLE}
                                     GROUP BY 1 ORDER BY 2 DESC""").fetchall():
        print(f"    {source:<18}{n:>10,}")
    return table_count(con, TABLE)


def main():
    con = connect()
    try:
        load(con)
    finally:
        con.close()
    print("DONE_LOAD_SYSTEM_CATALOG_ALIAS")


if __name__ == "__main__":
    main()

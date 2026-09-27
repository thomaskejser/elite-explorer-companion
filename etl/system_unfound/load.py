import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (connect, merge_counts, prepare_table, report_merge,
                       run_sql_file, table_count, transform_file)

HERE = pathlib.Path(__file__).resolve().parent
TABLE = "system_unfound"
SOURCE = "main.system_catalog + staging.catalog_parallax"


def load(con):
    before = prepare_table(con, TABLE, SOURCE)
    if not con.execute("""SELECT count(*) FROM duckdb_tables()
                          WHERE schema_name = 'staging'
                            AND table_name = 'catalog_parallax'""").fetchone()[0]:
        sys.exit("staging.catalog_parallax is missing -- it carries the astrometry this "
                 "table is built from, and nothing in etl/ stages it.")

    run_sql_file(con, transform_file(TABLE))
    print(f"transform.{TABLE}: {table_count(con, f'transform.{TABLE}'):,} candidate(s)")
    for band, typ, n in con.execute(f"""SELECT band, type, count(*) FROM transform.{TABLE}
                                        GROUP BY 1, 2 ORDER BY 1, 3 DESC""").fetchall():
        print(f"    {band:<6}{typ:<5}{n:>8,}")

    inserted, updated = merge_counts(con, HERE / "counts.sql")
    run_sql_file(con, HERE / "load.sql")
    report_merge(TABLE, before, table_count(con, TABLE), inserted, updated, [])

    stale = run_sql_file(con, HERE / "stale.sql").fetchone()[0]
    if stale:
        run_sql_file(con, HERE / "delete.sql")
        print(f"  DELETED {stale:,} row(s) the transform does not produce -- each "
              f"resolves by name or alias, or is in a dump, so it is not unfound.")

    print("\n  the strongest candidates -- 'near', with something to fly to:")
    print(f"    {'system':<14}{'ly':>8}{'snr':>7}{'Vmag':>7} {'type':<9}{'nearest':<24}"
          f"{'hop':>7}")
    for s, ly, snr, vmag, sp, near, hop in run_sql_file(con, HERE / "candidates.sql"
                                                         ).fetchall():
        print(f"    {s:<14}{ly:>8.1f}{snr:>7.1f}{(vmag or 0):>7.2f} {sp[:9]:<9}"
              f"{near[:23]:<24}{(hop if hop is not None else float('nan')):>7.2f}")
    return table_count(con, TABLE)


def main():
    con = connect()
    try:
        load(con)
    finally:
        con.close()
    print("DONE_LOAD_SYSTEM_UNFOUND")


if __name__ == "__main__":
    main()

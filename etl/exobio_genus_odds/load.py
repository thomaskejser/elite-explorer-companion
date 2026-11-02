import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (connect, merge_counts, prepare_table, report_merge,
                       run_sql_file, table_count, transform_file)

HERE = pathlib.Path(__file__).resolve().parent
TABLE = "exobio_genus_odds"


def load(con):
    before = prepare_table(con, TABLE, "transform.exobio_body + staging.canonn_codex_event "
                                       "+ main.exobio_species")
    if not con.execute("""SELECT count(*) FROM duckdb_tables()
                          WHERE schema_name = 'transform' AND table_name = 'exobio_body'""").fetchone()[0]:
        sys.exit("transform.exobio_body does not exist -- run python etl/exobio_odds/refresh.py first")
    if not table_count(con, "exobio_species"):
        sys.exit("main.exobio_species is empty -- run python etl/exobio_species/refresh.py")

    print("\nfitting each genus's share per cell...", flush=True)
    run_sql_file(con, transform_file(TABLE))
    rows, genera = con.execute("""SELECT count(*), count(DISTINCT genus)
                                  FROM transform.exobio_genus_odds""").fetchone()
    print(f"  {rows:,} cell-genus rows over {genera} genera")

    inserted, updated = merge_counts(con, HERE / "counts.sql")
    run_sql_file(con, HERE / "load.sql")
    orphans = ["/".join(str(c) for c in r)
               for r in run_sql_file(con, HERE / "orphans.sql").fetchall()]
    after = table_count(con, TABLE)
    report_merge(TABLE, before, after, inserted, updated, orphans)

    print(f"\n  {'genus':<20}{'cells':>7}{'bodies':>9}{'best share':>12}{'mean cr':>14}")
    for r in con.execute(f"""SELECT genus, count(*), sum(bodies), max(share), round(avg(cr_genus))
                             FROM {TABLE} WHERE star = '*'
                             GROUP BY genus ORDER BY sum(bodies) DESC""").fetchall():
        print(f"  {r[0]:<20}{r[1]:>7,}{r[2]:>9,}{r[3]:>12.2f}{int(r[4]):>14,}")
    return after


def main():
    con = connect(memory_limit="10GB")
    try:
        load(con)
    finally:
        con.close()
    print("DONE_LOAD_EXOBIO_GENUS_ODDS")


if __name__ == "__main__":
    from common.runlog import start
    start()
    main()

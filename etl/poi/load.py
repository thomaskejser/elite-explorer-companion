import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (connect, merge_counts, prepare_table, report_merge,
                       run_sql_file, table_count, transform_file)

HERE = pathlib.Path(__file__).resolve().parent
TABLE = "poi"
STAGED = "staging.poi_curated"
LINKS = (("poi_link_system", "system_known"), ("poi_link_body", "system_body"))


def link_views(con):
    built = {r[0] for r in con.execute(
        "SELECT table_name FROM duckdb_tables() WHERE schema_name = 'main'").fetchall()}
    for view, table in LINKS:
        source = (f"SELECT poi_id FROM main.{table} WHERE poi_id IS NOT NULL"
                  if table in built else "SELECT CAST(NULL AS INTEGER) AS poi_id WHERE false")
        con.execute(f"CREATE OR REPLACE TEMP VIEW {view} AS {source}")
        if table not in built:
            print(f"  main.{table} not built yet: its {TABLE} count stays NULL")


def load(con):
    before = prepare_table(con, TABLE, STAGED)

    link_views(con)
    run_sql_file(con, transform_file(TABLE))
    n_src = table_count(con, "transform.poi")
    print(f"transform.poi: {n_src:,} row(s)")

    inserted, updated = merge_counts(con, HERE / "counts.sql")
    run_sql_file(con, HERE / "load.sql")

    orphans = [f"poi_id={r[0]:<5} {r[1]}"
               for r in run_sql_file(con, HERE / "orphans.sql").fetchall()]
    after = table_count(con, TABLE)
    report_merge(TABLE, before, after, inserted, updated, orphans)

    uncurated = run_sql_file(con, HERE / "uncurated.sql").fetchall()
    if uncurated:
        print(f"\n  {len(uncurated):,} kind(s) named by a feed but absent from "
              f"input/poi.parquet -- NOT merged, because which of them is a POI is a "
              f"curation decision. Add the ones worth flying to, with an unused poi_id:")
        for poi, src, reports in uncurated[:15]:
            print(f"    {poi[:44]:<45}{src:<14}{reports:>9,} report(s)")
        if len(uncurated) > 15:
            print(f"    ... and {len(uncurated) - 15:,} more")

    print(f"\n  {'class':<10}{'kinds':>7}{'landing':>9}{'systems':>12}{'bodies':>12}")
    for r in con.execute(f"""
            SELECT poi_class, count(*), count(*) FILTER (WHERE needs_landing),
                   sum(systems), sum(bodies)
            FROM {TABLE} GROUP BY 1 ORDER BY 1""").fetchall():
        f = lambda v: "-" if v is None else f"{v:,}"
        print(f"  {r[0]:<10}{r[1]:>7}{r[2]:>9}{f(r[3]):>12}{f(r[4]):>12}")
    return after


def main():
    con = connect()
    try:
        load(con)
    finally:
        con.close()
    print("DONE_LOAD_POI")


if __name__ == "__main__":
    from common.runlog import start
    start()
    main()

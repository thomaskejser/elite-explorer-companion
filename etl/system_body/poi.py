import sys, pathlib, importlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (check_references, connect, merge_counts, report_merge,
                       run_sql_file, table_count)
from common.poi_link import stage_poi_events, winner_sql

HERE = pathlib.Path(__file__).resolve().parent
TABLE = "system_body"
load = importlib.import_module("etl.system_body.load")


def link(con):
    load.live_shape(con)
    print("linking body-level POIs...", flush=True)
    stage_poi_events(con)
    con.execute(f"""CREATE OR REPLACE TABLE staging.poi_body AS
        {winner_sql(['system_id', 'body_suffix'], 'body_suffix IS NOT NULL')}""")
    run_sql_file(con, HERE / "poi_alloc.sql")
    print(f"    {table_count(con, 'staging.poi_body_merge'):,} (system, body) POIs")

    before = table_count(con, TABLE)
    inserted, updated, cleared, virgin = merge_counts(con, HERE / "poi_counts.sql")
    print(f"    {virgin:,} of those systems have NO body row and will LEAVE "
          f"system_predicted")
    run_sql_file(con, HERE / "poi.sql")
    after = table_count(con, TABLE)
    report_merge(TABLE, before, after, inserted, updated, [],
                 extra=f", {cleared:,} stale id_poi cleared")

    check_references(con, TABLE)
    dual = con.execute(f"""SELECT count(*) FROM (SELECT system_id FROM {TABLE}
                           WHERE is_primary GROUP BY 1 HAVING count(*) > 1)""").fetchone()[0]
    print(f"    systems with >1 is_primary row: {dual:,}"
          + ("  <== BROKEN" if dual else "  (ok)"))
    print(con.execute(f"""SELECT p.poi_class, count(*) AS bodies FROM {TABLE} b
                          JOIN main.poi p ON p.poi_id = b.id_poi
                          GROUP BY 1 ORDER BY 2 DESC""").fetchdf().to_string(index=False))
    return inserted + updated + cleared


def main():
    con = connect(memory_limit="6GB", threads=8)
    try:
        link(con)
    finally:
        con.close()
    print("DONE_LINK_POI_SYSTEM_BODY")


if __name__ == "__main__":
    main()

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import check_references, connect, merge_counts, run_sql_file, table_count
from common.poi_link import stage_poi_events, winner_sql

HERE = pathlib.Path(__file__).resolve().parent


def link(con):
    print("linking system-level POIs...", flush=True)
    stage_poi_events(con)
    con.execute(f"""CREATE OR REPLACE TABLE staging.poi_sys AS
                    {winner_sql(['system_id'], 'body_suffix IS NULL')}""")
    print(f"    {table_count(con, 'staging.poi_sys'):,} systems get a system-level "
          f"id_poi (rarest POI wins)")

    updated, cleared = merge_counts(con, HERE / "poi_counts.sql")
    run_sql_file(con, HERE / "poi.sql")
    print(f"    {updated:,} id_poi set, {cleared:,} stale id_poi cleared")

    check_references(con, "system_known")
    print(con.execute("""SELECT p.poi_class, count(*) AS systems FROM main.system_known k
                         JOIN main.poi p ON p.poi_id = k.id_poi
                         GROUP BY 1 ORDER BY 2 DESC""").fetchdf().to_string(index=False))
    return updated + cleared


def main():
    con = connect(memory_limit="6GB", threads=8)
    try:
        link(con)
    finally:
        con.close()
    print("DONE_LINK_POI_SYSTEM_KNOWN")


if __name__ == "__main__":
    main()

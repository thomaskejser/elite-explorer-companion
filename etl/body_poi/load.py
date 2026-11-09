import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (connect, merge_counts, prepare_table, report_merge,
                       run_sql_file, table_count, transform_file)

HERE = pathlib.Path(__file__).resolve().parent
TABLE = "body_poi"
SOURCE = "main.system_body + staging.edastro_point_of_interest"


def load(con):
    before = prepare_table(con, TABLE, SOURCE)

    print("  placing POIs on bodies (scans system_body -- minutes, not seconds)...", flush=True)
    run_sql_file(con, transform_file(TABLE))

    for source, rows, systems in con.execute("""
            SELECT source, count(*), count(DISTINCT system_id)
            FROM transform.body_poi GROUP BY 1 ORDER BY 1""").fetchall():
        print(f"transform.body_poi: {rows:,} from {source} over {systems:,} system(s)")

    inserted, updated = merge_counts(con, HERE / "counts.sql")
    run_sql_file(con, HERE / "load.sql")

    orphans = [f"system_id={r[0]} body={r[1]} poi_id={r[2]}"
               for r in run_sql_file(con, HERE / "orphans.sql").fetchall()[:20]]
    after = table_count(con, TABLE)
    report_merge(TABLE, before, after, inserted, updated, orphans)
    return after


def main():
    con = connect()
    try:
        load(con)
    finally:
        con.close()
    print("DONE_LOAD_BODY_POI")


if __name__ == "__main__":
    from common.runlog import start
    start()
    main()

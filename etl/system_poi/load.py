import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (check_references, connect, merge_counts, prepare_table,
                       report_merge, run_sql_file, table_count, transform_file)

HERE = pathlib.Path(__file__).resolve().parent
TABLE = "system_poi"
SOURCE = "main.system_known + main.system_body"


def load(con):
    before = prepare_table(con, TABLE, SOURCE)

    print("  unioning the two POI attributions "
          "(scans system_body -- minutes, not seconds)...", flush=True)
    run_sql_file(con, transform_file(TABLE))

    n_src, n_sys, n_level, n_body = con.execute("""
        SELECT (SELECT count(*) FROM transform.system_poi),
               (SELECT count(DISTINCT system_id) FROM transform.system_poi),
               (SELECT count(*) FROM main.system_known WHERE id_poi IS NOT NULL),
               (SELECT count(*) FROM main.system_body  WHERE id_poi IS NOT NULL)
        """).fetchone()
    print(f"transform.system_poi: {n_src:,} (system, POI) pair(s) over {n_sys:,} system(s)")
    print(f"  from {n_level:,} system-level and {n_body:,} body-level attribution(s)")

    inserted, updated = merge_counts(con, HERE / "counts.sql")
    run_sql_file(con, HERE / "load.sql")

    orphans = [f"system_id={r[0]} poi_id={r[1]} {r[2]}"
               for r in run_sql_file(con, HERE / "orphans.sql").fetchall()[:20]]
    after = table_count(con, TABLE)
    report_merge(TABLE, before, after, inserted, updated, orphans)

    print("\nreferential integrity:")
    check_references(con, TABLE)

    print(f"\n  {'POI':<34}{'systems':>10}")
    for r in con.execute(f"""
            SELECT p.poi, count(*) FROM {TABLE} sp JOIN main.poi p USING (poi_id)
            GROUP BY 1 ORDER BY 2 DESC LIMIT 10""").fetchall():
        print(f"  {r[0][:33]:<34}{r[1]:>10,}")

    missing = con.execute(f"SELECT count(*) FROM {TABLE} WHERE x IS NULL").fetchone()[0]
    print(f"\n  without coordinates: {missing:,} -- cannot be ranked by distance")
    return after


def main():
    con = connect()
    try:
        load(con)
    finally:
        con.close()
    print("DONE_LOAD_SYSTEM_POI")


if __name__ == "__main__":
    main()

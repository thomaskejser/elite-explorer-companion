import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import connect, run_sql_file, staging_file, table_count
from common.sources import download

URL = "https://raw.githubusercontent.com/klightspeed/EliteDangerousRegionMap/master/RegionMapData.json"
RAW_NAME = "klightspeed_RegionMapData.json"
TABLE = "staging.klightspeed_region_map"

DECODE = """
INSERT INTO staging.klightspeed_region_map (z_row, run_no, length, region)
WITH d AS (SELECT regions, regionmap
           FROM read_json('{path}', columns = {{regions: 'VARCHAR[]', regionmap: 'INTEGER[][][]'}})),
r AS (SELECT regions, unnest(regionmap) AS runs, generate_subscripts(regionmap, 1) - 1 AS z_row FROM d),
u AS (SELECT regions, z_row, unnest(runs) AS run, generate_subscripts(runs, 1) AS run_no FROM r)
SELECT z_row, run_no, run[1], regions[run[2] + 1] FROM u
"""


def stage(con):
    path = download(URL, RAW_NAME, min_bytes=100_000)
    run_sql_file(con, staging_file("klightspeed_region_map"))
    con.execute("BEGIN TRANSACTION")
    try:
        con.execute(f"TRUNCATE {TABLE}")
        con.execute(DECODE.format(path=path.as_posix()))
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    n = table_count(con, TABLE)
    rows, widths = con.execute(f"""SELECT count(DISTINCT z_row), count(DISTINCT w) FROM (
                                       SELECT z_row, sum(length) OVER (PARTITION BY z_row) AS w FROM {TABLE})"""
                               ).fetchone()
    print(f"{TABLE}: {n:,} run(s) over {rows:,} row(s)")
    if rows != 2048 or widths != 1:
        sys.exit(f"{TABLE}: expected 2,048 rows of 2,048 cells each -- the source has changed shape")
    return n


def main():
    con = connect()
    try:
        stage(con)
    finally:
        con.close()
    print("DONE_STAGE_REGION_MAP")


if __name__ == "__main__":
    from common.runlog import start
    start()
    main()

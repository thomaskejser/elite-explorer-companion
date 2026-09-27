import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import connect, run_sql_file, staging_file
from common.sources import download

URL = "https://edastro.com/mapcharts/files/fleetcarriers.csv"
RAW_NAME = "edastro_fleet_carrier.csv"
NAME = "edastro_fleet_carrier"
TABLE = f"staging.{NAME}"

COLUMNS = """
    "Callsign", "Name", "Owner", "LastUpdated", "LastMoved", "LastSystem",
    "SystemAddress", "Coord_X", "Coord_Y", "Coord_Z", "SolDistance",
    "EstimatedRegion", "LocationHistory", "DockingsEDDN", "Services"
"""


def _drop_view(con, name):
    if con.execute("""SELECT count(*) FROM duckdb_views()
                      WHERE schema_name = 'staging' AND view_name = ?""",
                   [name]).fetchone()[0]:
        con.execute(f"DROP VIEW staging.{name}")


def stage(con):
    path = download(URL, RAW_NAME, min_bytes=1_000_000)
    _drop_view(con, NAME)
    run_sql_file(con, staging_file(NAME))
    con.execute("BEGIN TRANSACTION")
    try:
        con.execute(f"TRUNCATE {TABLE}")
        con.execute(f"""INSERT INTO {TABLE}
                        SELECT {COLUMNS}
                        FROM read_csv_auto('{path.as_posix()}', header=true)""")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    n, repeated = con.execute(f"""
        SELECT (SELECT count(*) FROM {TABLE}),
               (SELECT count(*) FROM (SELECT Callsign FROM {TABLE}
                                      GROUP BY 1 HAVING count(*) > 1))""").fetchone()
    print(f"{TABLE}: {n:,} row(s), {repeated:,} callsign(s) reported more than once")
    return n


def main():
    con = connect()
    try:
        stage(con)
    finally:
        con.close()
    print("DONE_STAGE_CARRIER")


if __name__ == "__main__":
    main()

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import connect, run_sql_file, staging_file, table_count
from common.sources import download

URL = "https://edastro.com/mapcharts/files/sector-list.csv"
RAW_NAME = "edastro_sector-list.csv"
TABLE = "staging.edastro_sector"

COLUMNS = """
    "Sector", "Systems", "Avg X", "Avg Y", "Avg Z",
    "Min X", "Min Y", "Min Z", "Max X", "Max Y", "Max Z",
    "MapSector X", "MapSector Y", "First Encountered",
    "id64 X", "id64 Y", "id64 Z"
"""


def stage(con):
    path = download(URL, RAW_NAME, min_bytes=100_000)
    run_sql_file(con, staging_file("edastro_sector"))
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
    n = table_count(con, TABLE)
    cells = con.execute(f"SELECT count(*) FROM {TABLE} WHERE id64_x IS NULL").fetchone()[0]
    print(f"{TABLE}: {n:,} row(s), {cells:,} with no id64 grid cell")
    return n


def main():
    con = connect()
    try:
        stage(con)
    finally:
        con.close()
    print("DONE_STAGE_SECTOR")


if __name__ == "__main__":
    main()

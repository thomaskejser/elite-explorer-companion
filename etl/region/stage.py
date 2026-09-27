import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import connect, run_sql_file, staging_file, table_count
from common.sources import download

URL = "https://storage.googleapis.com/canonn-downloads/codex.json.gz"
RAW_NAME = "canonn_codex_event.json.gz"
TABLE = "staging.canonn_codex_event"


def stage(con):
    path = download(URL, RAW_NAME, min_bytes=1_000_000)
    run_sql_file(con, staging_file("canonn_codex_event"))
    con.execute("BEGIN TRANSACTION")
    try:
        con.execute(f"TRUNCATE {TABLE}")
        con.execute(f"""INSERT INTO {TABLE} BY NAME
                        SELECT * FROM read_json_auto('{path.as_posix()}',
                                                     ignore_errors=true)""")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    n = table_count(con, TABLE)
    print(f"{TABLE}: {n:,} row(s)")
    return n


def main():
    con = connect()
    try:
        stage(con)
    finally:
        con.close()
    print("DONE_STAGE_REGION")


if __name__ == "__main__":
    main()

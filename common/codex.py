from common.db import run_sql_file, staging_file, table_count
from common.sources import download

FEEDS = [
    ("canonn_codex_event", "https://storage.googleapis.com/canonn-downloads/codex.json.gz",
     "canonn_codex_event.json.gz", 1_000_000),
    ("edsm_codex_entry", "https://www.edsm.net/dump/codex.json.gz",
     "edsm_codex_entry.json.gz", 1_000_000),
    ("edastro_point_of_interest", "https://edastro.com/gec/json/combined",
     "edastro_point_of_interest.json", 100_000),
]


def drop_view(con, name):
    if con.execute("""SELECT count(*) FROM duckdb_views()
                      WHERE schema_name = 'staging' AND view_name = ?""",
                   [name]).fetchone()[0]:
        con.execute(f"DROP VIEW staging.{name}")


def replace_rows(con, table, select):
    con.execute("BEGIN TRANSACTION")
    try:
        con.execute(f"TRUNCATE {table}")
        con.execute(f"INSERT INTO {table} {select}")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    n = table_count(con, table)
    print(f"{table}: {n:,} row(s)")
    return n


def stage_codex_feeds(con):
    for name, url, raw, floor in FEEDS:
        path = download(url, raw, min_bytes=floor)
        drop_view(con, name)
        run_sql_file(con, staging_file(name))
        replace_rows(con, f"staging.{name}",
                     f"""BY NAME SELECT * FROM read_json_auto('{path.as_posix()}',
                                                              ignore_errors=true)""")

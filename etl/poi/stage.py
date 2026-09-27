import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import INPUT, connect, run_sql_file, staging_file
from common.codex import replace_rows, stage_codex_feeds

CURATED = INPUT / "poi.parquet"
CURATED_TABLE = "staging.poi_curated"
CURATED_COLUMNS = "poi_id, poi, poi_class, poi_family, needs_landing, sources"


def stage(con):
    stage_codex_feeds(con)

    if not CURATED.exists():
        sys.exit(f"missing {CURATED} -- it is authoritative and hand-edited, and there\n"
                 f"is no seeder that will recreate it. Restore it from git.")
    run_sql_file(con, staging_file("poi_curated"))
    replace_rows(con, CURATED_TABLE,
                 f"SELECT {CURATED_COLUMNS} FROM '{CURATED.as_posix()}'")


def main():
    con = connect()
    try:
        stage(con)
    finally:
        con.close()
    print("DONE_STAGE_POI")


if __name__ == "__main__":
    main()

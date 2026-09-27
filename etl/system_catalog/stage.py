import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import INPUT, connect, run_sql_file, staging_file, table_count

SOURCE = INPUT / "system_catalog.parquet"
TABLE = "staging.system_catalog_curated"


def stage(con):
    if not SOURCE.exists():
        sys.exit(f"missing {SOURCE} -- it is authoritative and hand-editable. Restore it "
                 f"from git, or seed it once with: python etl/system_catalog/seed.py")
    run_sql_file(con, staging_file("system_catalog_curated"))
    con.execute("BEGIN TRANSACTION")
    try:
        con.execute(f"TRUNCATE {TABLE}")
        con.execute(f"""INSERT INTO {TABLE} (system, type, designation)
                        SELECT system, type, designation FROM '{SOURCE.as_posix()}'""")
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
    print("DONE_STAGE_SYSTEM_CATALOG")


if __name__ == "__main__":
    main()

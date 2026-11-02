import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import INPUT, connect, run_sql_file, staging_file, table_count

SOURCE = INPUT / "system_catalog.parquet"
TABLE = "staging.system_catalog_curated"
COMMANDER = INPUT / "commander_alias.parquet"
COMMANDER_TABLE = "staging.commander_alias"


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
    stage_commander(con)
    return n


def stage_commander(con):
    run_sql_file(con, staging_file("commander_alias"))
    con.execute(f"TRUNCATE {COMMANDER_TABLE}")
    if not COMMANDER.exists():
        print(f"{COMMANDER_TABLE}: none -- {COMMANDER.name} is written by scripts/export_commander_aliases.py")
        return 0
    con.execute(f"""INSERT INTO {COMMANDER_TABLE} (system, canonical, system_id, asserted_utc)
                    SELECT system, canonical, system_id, asserted_utc FROM '{COMMANDER.as_posix()}'""")
    n = table_count(con, COMMANDER_TABLE)
    print(f"{COMMANDER_TABLE}: {n:,} row(s)")
    return n


def main():
    con = connect()
    try:
        stage(con)
    finally:
        con.close()
    print("DONE_STAGE_SYSTEM_CATALOG")


if __name__ == "__main__":
    from common.runlog import start
    start()
    main()

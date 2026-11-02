import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (check_references, connect, merge_counts, prepare_table,
                       report_merge, run_sql_file, table_count, transform_file)

HERE = pathlib.Path(__file__).resolve().parent
TABLE = "codex_sighting"
SOURCE = "staging.edsm_codex_entry + canonn_codex_event"


def load(con):
    before = prepare_table(con, TABLE, SOURCE)
    if not table_count(con, "main.system_known"):
        raise SystemExit("main.system_known is empty -- run: python etl/system_known/refresh.py")

    no_region, no_system = run_sql_file(con, HERE / "skipped.sql").fetchone()
    print(f"EDSM codex reports left out: {no_region:,} with a region name main.region lacks, "
          f"{no_system:,} whose id64 is not in system_known", flush=True)

    print("reducing reports to (entry, region, sector)...", flush=True)
    run_sql_file(con, transform_file(TABLE))
    print(f"transform.{TABLE}: {table_count(con, f'transform.{TABLE}'):,} row(s)")

    inserted, updated = merge_counts(con, HERE / "counts.sql")
    run_sql_file(con, HERE / "load.sql")
    after = table_count(con, TABLE)
    report_merge(TABLE, before, after, inserted, updated, [])
    stale = run_sql_file(con, HERE / "orphans.sql").fetchone()[0]
    if stale:
        print(f"  {stale:,} row(s) the source no longer produces -- LEFT IN PLACE, "
              f"a sighting stays reported")

    print("\nreferential integrity:")
    check_references(con, TABLE)

    print("\nby category:")
    print(con.execute(f"""
        SELECT category, count(DISTINCT codex) AS entries, count(DISTINCT (codex, region_id)) AS in_regions,
               sum(systems) AS systems
        FROM {TABLE} GROUP BY 1 ORDER BY 1""").fetchdf().to_string(index=False))
    return after


def main():
    con = connect(memory_limit="8GB")
    try:
        load(con)
    finally:
        con.close()
    print("DONE_LOAD_CODEX_SIGHTING")


if __name__ == "__main__":
    from common.runlog import start
    start()
    main()

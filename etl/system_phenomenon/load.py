import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (check_references, connect, merge_counts, prepare_table,
                       report_merge, run_sql_file, table_count, transform_file)

HERE = pathlib.Path(__file__).resolve().parent
TABLE = "system_phenomenon"
SOURCE = "staging.canonn_codex_event + edsm_codex_entry + edastro_point_of_interest"


def load(con):
    before = prepare_table(con, TABLE, SOURCE)
    if not table_count(con, "main.system_known"):
        raise SystemExit("main.system_known is empty -- run: "
                         "python etl/system_known/refresh.py")

    print("classifying codex and GEC observations...", flush=True)
    run_sql_file(con, transform_file("ph_obs"))
    print(f"transform.ph_obs: {table_count(con, 'transform.ph_obs'):,} report(s)")

    print("collapsing to (system, phenomenon)...", flush=True)
    run_sql_file(con, transform_file(TABLE))
    for ph, n, res in run_sql_file(con, HERE / "resolution.sql").fetchall():
        print(f"  {ph}: {n:,} systems, {res:,} resolved to system_known "
              f"({n - res:,} unresolved, left out)")

    inserted, updated = merge_counts(con, HERE / "counts.sql")
    run_sql_file(con, HERE / "load.sql")

    after = table_count(con, TABLE)
    report_merge(TABLE, before, after, inserted, updated, [])
    orphans = run_sql_file(con, HERE / "orphans.sql").fetchall()
    for ph, n in orphans:
        print(f"  {ph}: {n:,} row(s) not produced by the sources -- LEFT IN "
              f"PLACE, this table records, it does not predict")

    print("\nreferential integrity:")
    check_references(con, TABLE)

    print("\nby phenomenon:")
    print(con.execute(f"""
        SELECT phenomenon, count(*) AS systems, sum(observations) AS obs,
               count(*) FILTER (WHERE from_canonn) AS canonn,
               count(*) FILTER (WHERE from_edsm)   AS edsm,
               count(*) FILTER (WHERE from_gec)    AS gec
        FROM {TABLE} GROUP BY 1 ORDER BY 1""").fetchdf().to_string(index=False))
    return after


def main():
    con = connect(memory_limit="8GB")
    try:
        load(con)
    finally:
        con.close()
    print("DONE_LOAD_SYSTEM_PHENOMENON")


if __name__ == "__main__":
    main()

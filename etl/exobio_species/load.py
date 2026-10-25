import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (connect, merge_counts, prepare_table, report_merge,
                       run_sql_file, table_count, transform_file)

HERE = pathlib.Path(__file__).resolve().parent
TABLE = "exobio_species"


def load(con):
    before = prepare_table(con, TABLE,
                           "staging.exobio_species_curated + staging.canonn_codex_event")
    run_sql_file(con, transform_file(TABLE))
    print(f"transform.{TABLE}: {table_count(con, 'transform.' + TABLE):,} row(s)")

    inserted, updated = merge_counts(con, HERE / "counts.sql")
    run_sql_file(con, HERE / "load.sql")
    orphans = [f"{r[0]}  {r[1]}" for r in run_sql_file(con, HERE / "orphans.sql").fetchall()]
    after = table_count(con, TABLE)
    report_merge(TABLE, before, after, inserted, updated, orphans)

    unseen = [r[0] for r in con.execute(f"""SELECT species FROM {TABLE}
                                            WHERE bodies_codexed = 0 ORDER BY 1""").fetchall()]
    print(f"  species no Canonn report names: {len(unseen)}"
          + (f" ({', '.join(unseen)})" if unseen else ""))
    return after


def main():
    con = connect()
    try:
        load(con)
    finally:
        con.close()
    print("DONE_LOAD_EXOBIO_SPECIES")


if __name__ == "__main__":
    from common.runlog import start
    start()
    main()

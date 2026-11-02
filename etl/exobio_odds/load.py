import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (connect, merge_counts, prepare_table, report_merge,
                       run_sql_file, table_count, transform_file)

HERE = pathlib.Path(__file__).resolve().parent
TABLE = "exobio_odds"
BUCKETS = 8
FEEDS = ("spansh_galaxy_body", "spansh_galaxy_1month_body", "spansh_galaxy_1day_body",
         "canonn_codex_event")


def build_bodies(con):
    missing = [t for t in FEEDS if not con.execute(
        """SELECT count(*) FROM duckdb_tables()
           WHERE schema_name = 'staging' AND table_name = ?""", [t]).fetchone()[0]]
    if missing:
        sys.exit(f"staging is missing {', '.join(missing)} -- stage them with "
                 f"python etl/system_known/refresh.py and python etl/region/refresh.py")
    print(f"\nreducing the Spansh body feeds to thin-atmosphere planets "
          f"in {BUCKETS} buckets...", flush=True)
    run_sql_file(con, transform_file("exobio_feed"))
    print(f"  {table_count(con, 'transform.exobio_feed'):,} reports staged", flush=True)
    run_sql_file(con, transform_file("exobio_body"))
    for bucket in range(BUCKETS):
        run_sql_file(con, HERE / "body.sql", [BUCKETS, bucket])
        print(f"  bucket {bucket + 1}/{BUCKETS}: "
              f"{table_count(con, 'transform.exobio_body'):,} bodies so far", flush=True)
    for status, n in con.execute("""SELECT status, count(*) FROM transform.exobio_body
                                    GROUP BY 1 ORDER BY 2 DESC""").fetchall():
        print(f"  {status:<16}{n:>12,}")


def load(con):
    before = prepare_table(con, TABLE, "transform.exobio_body + staging.canonn_codex_event "
                                       "+ main.exobio_species")
    if not table_count(con, "exobio_species"):
        sys.exit("main.exobio_species is empty -- run python etl/exobio_species/refresh.py")
    build_bodies(con)

    print("\nfitting the odds per cell...", flush=True)
    run_sql_file(con, transform_file(TABLE))
    cells, wide = con.execute("""SELECT count(*), count(*) FILTER (WHERE star = '*')
                                 FROM transform.exobio_odds""").fetchone()
    print(f"  {cells:,} cells, {wide:,} of them over every star")

    inserted, updated = merge_counts(con, HERE / "counts.sql")
    run_sql_file(con, HERE / "load.sql")
    orphans = ["/".join(str(c) for c in r)
               for r in run_sql_file(con, HERE / "orphans.sql").fetchall()]
    after = table_count(con, TABLE)
    report_merge(TABLE, before, after, inserted, updated, orphans)

    print(f"\n  {'atmosphere':<24}{'body type':<26}{'band':>5}{'bodies':>10}"
          f"{'p_bio':>7}{'cr_bio':>13}  likely")
    for r in con.execute(f"""SELECT atmosphere, body_type, temp_band, bodies, p_bio, cr_bio,
                                    likely_species
                             FROM {TABLE} WHERE star = '*' AND bodies >= 10000
                             ORDER BY p_bio * coalesce(cr_bio, 0) DESC LIMIT 12""").fetchall():
        print(f"  {r[0]:<24}{r[1]:<26}{r[2]:>5}{r[3]:>10,}{r[4]:>7.2f}{(r[5] or 0):>13,}  {r[6]}")
    return after


def main():
    con = connect(memory_limit="10GB")
    try:
        load(con)
    finally:
        con.close()
    print("DONE_LOAD_EXOBIO_ODDS")


if __name__ == "__main__":
    from common.runlog import start
    start()
    main()

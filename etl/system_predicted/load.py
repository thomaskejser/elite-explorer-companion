import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (connect, merge_counts, prepare_table, report_merge,
                       run_sql_file, staging_file, table_count, transform_file)

HERE = pathlib.Path(__file__).resolve().parent
TABLE = "system_predicted"
SOURCE = "main.system_known + main.system_body"
WR_BASIS = {1: ">=90% boxels", 2: ">=80% boxels", 3: "all scanned"}
CROSS_TARGETS = ("bh", "wr", "neutron", "wd", "herbig", "otype", "supergiant")


def build(con, name, what):
    print(f"\n{what}...", flush=True)
    run_sql_file(con, transform_file(name))
    return table_count(con, f"transform.{name}")


def scan_value(con, refresh):
    have = con.execute("""SELECT count(*) FROM duckdb_tables()
                          WHERE schema_name='staging'
                            AND table_name='sys_value'""").fetchone()[0]
    if have and not run_sql_file(con, HERE / "value_probe.sql").fetchone()[0]:
        print("\n  no sampled system_id in staging.sys_value resolves in "
              "main.system_known -- RECOMPUTING it.", flush=True)
        have = 0
    if have and not refresh:
        print("\nreusing staging.sys_value (pass --refresh-value to recompute)",
              flush=True)
        return
    print("\ncomputing per-system scan value (570M-row pass)...", flush=True)
    run_sql_file(con, staging_file("sys_value"))


def load(con, refresh_value=False):
    before = prepare_table(con, TABLE, SOURCE)

    build(con, "pred_labels", "labelling systems from system_body JOIN body")
    r = con.execute("""SELECT count(*),
                              count(*) FILTER (WHERE n_scan_rows > 0 AND n_stars > 0)
                       FROM transform.pred_labels""").fetchone()
    print(f"  {r[0]:,} systems labelled, {r[1]:,} qualify as SCANNED "
          f"({r[0] - r[1]:,} excluded: catalogue-only or no star)")

    build(con, "pred_boxel_scan", "measuring boxel scan completeness")
    for r in con.execute("""SELECT mass_code, count(*),
                                   count(*) FILTER (WHERE scanned >= 10 AND frac >= 0.90),
                                   round(avg(frac), 4)
                            FROM transform.pred_boxel_scan
                            GROUP BY 1 ORDER BY 1""").fetchall():
        print(f"    mc={r[0]}  boxels {r[1]:>8,}  fully-explored {r[2]:>7,}  "
              f"mean scanned {r[3]:.1%}")

    build(con, "pred_rate",
          "fitting empirical rates by (mass_code, plane_r band), OUTSIDE the cross")
    build(con, "pred_cross",
          "measuring the cross (suppression near the x=0 / z=0 planes)")
    print(f"  {'band':<12}{'systems':>10}" + "".join(f"{c:>11}" for c in CROSS_TARGETS))
    for r in con.execute("SELECT cross_band, n, "
                         + ", ".join(f"f_{c}" for c in CROSS_TARGETS)
                         + " FROM transform.pred_cross ORDER BY lo").fetchall():
        print(f"  {r[0]:<12}{r[1]:>10,}" + "".join(f"{v:>10.3f}x" for v in r[2:]))

    print(f"  {'mc':<4}{'band':<9}{'systems':>12}{'BH%':>8}{'WR%':>8}  "
          f"{'WR basis':<16}{'WR n':>10}")
    for r in con.execute("""SELECT mass_code, band, n, r_bh, r_wr, wr_tier, wr_n
                            FROM transform.pred_rate
                            ORDER BY mass_code, band""").fetchall():
        print(f"  {r[0]:<4}{r[1]:<9}{r[2]:>12,}{r[3]:>7.2%}{(r[4] or 0):>8.2%}  "
              f"{WR_BASIS.get(r[5], '-'):<16}{(r[6] or 0):>10,}")

    scan_value(con, refresh_value)
    build(con, "pred_value", "averaging scan value per mass code")
    comp = con.execute("SELECT any_value(completeness) "
                       "FROM transform.pred_value").fetchone()[0]
    print(f"  scan completeness {comp:.3%}  -> full-scan correction x{1/comp:.3f}")
    print(f"  {'mc':<4}{'systems':>12}{'exp bodies':>13}{'exp Cr (full scan)':>21}")
    for r in con.execute("""SELECT mass_code, n, exp_bodies, exp_scan_value_cr
                            FROM transform.pred_value ORDER BY 1""").fetchall():
        print(f"  {r[0]:<4}{r[1]:>12,}{r[2]:>13,.2f}{r[3]:>21,.0f}")

    n = build(con, "pred_boxel_gap", "enumerating boxel-index gaps from system_known")
    for r in con.execute("""SELECT mass_code, count(*) FROM transform.pred_boxel_gap
                            GROUP BY 1 ORDER BY 1""").fetchall():
        print(f"    mc={r[0]}: {r[1]:,}")
    print(f"    total: {n:,}")

    build(con, "pred_pool",
          "assembling the candidate pool (system_known MINUS system_body)")
    for r in con.execute("""SELECT is_catalog, count(*) FROM transform.pred_pool
                            GROUP BY 1 ORDER BY 1 DESC""").fetchall():
        print(f"  {'catalogued_unscanned' if r[0] else 'boxel-predicted':<24}"
              f"{r[1]:>12,}")
    dup = con.execute("""SELECT count(*) FROM (SELECT system_name FROM transform.pred_pool
                         GROUP BY 1 HAVING count(*) > 1)""").fetchone()[0]
    if dup:
        raise SystemExit(f"pool has {dup} duplicate system_name(s) -- refusing to merge "
                         f"on a non-unique natural key")

    build(con, TABLE, "scoring the pool")
    inserted, updated = merge_counts(con, HERE / "counts.sql")
    run_sql_file(con, HERE / "load.sql")
    merged = table_count(con, TABLE)
    report_merge(TABLE, before, merged, inserted, updated, [])

    stale = run_sql_file(con, HERE / "orphans.sql").fetchone()[0]
    if stale:
        run_sql_file(con, HERE / "delete.sql")
        print(f"\n  DELETED {stale:,} prediction(s) the pool does not produce -- their "
              f"systems have body rows, so they are not predictions. This table "
              f"deliberately deletes; see ETL.md.", flush=True)
    after = table_count(con, TABLE)
    print(f"  {merged:,} -> {after:,} rows after the delete")

    print(f"\n  {'is_catalog':<24}{'rows':>12}{'mean p_bh':>11}{'mean p_wr':>11}")
    for r in con.execute(f"""SELECT is_catalog, count(*), avg(p_bh), avg(p_wr)
                             FROM {TABLE} GROUP BY 1 ORDER BY 1 DESC""").fetchall():
        lab = "TRUE  (catalogued)" if r[0] else "FALSE (boxel-predicted)"
        print(f"  {lab:<24}{r[1]:>12,}{r[2]:>11.4f}{r[3]:>11.4f}")

    print(f"\n  {'mc':<4}{'rows':>12}{'p_bh':>9}{'p_wr':>9}{'p_herbig':>10}"
          f"{'exp Cr':>12}")
    for r in con.execute(f"""SELECT mass_code, count(*), avg(p_bh), avg(p_wr),
                                    avg(p_herbig), avg(exp_scan_value_cr)
                             FROM {TABLE} GROUP BY 1 ORDER BY 1""").fetchall():
        print(f"  {r[0]:<4}{r[1]:>12,}{r[2]:>9.4f}{r[3]:>9.4f}{r[4]:>10.4f}"
              f"{r[5]:>12,.0f}")

    nn = con.execute(f"""SELECT count(*) FROM {TABLE}
                         WHERE p_bh IS NULL OR exp_scan_value_cr IS NULL""").fetchone()[0]
    print(f"\n  rows missing a rate or value: {nn:,}"
          f"{'  <== CHECK the rate/value joins' if nn else '  (ok)'}")
    return after


def main():
    con = connect(memory_limit="8GB", threads=8)
    try:
        load(con, "--refresh-value" in sys.argv)
    finally:
        con.close()
    print("DONE_LOAD_SYSTEM_PREDICTED")


if __name__ == "__main__":
    main()

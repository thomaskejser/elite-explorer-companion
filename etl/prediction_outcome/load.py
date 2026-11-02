import sys, pathlib
from string import Template
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (connect, merge_counts, prepare_table, report_merge,
                       run_sql_file, table_count, transform_file)

HERE = pathlib.Path(__file__).resolve().parent
TABLE = "prediction_outcome"
SOURCE = "main.system_predicted + staging.pred_snapshot_* against main.system_known + main.system_body"
KINDS = ("bh", "wr", "neutron", "wd", "herbig", "otype", "supergiant")
MIN_CELL = 100
COLUMNS = ("system, is_catalog, system_id, sector, mass_code, x, y, z, p_bh, p_wr, p_neutron, "
           "p_wd, p_herbig, p_otype, p_supergiant, exp_bodies")


def sources(con):
    snapshots = [r[0] for r in con.execute("""SELECT table_name FROM duckdb_tables()
                                              WHERE schema_name = 'staging'
                                                AND table_name LIKE 'pred_snapshot_%'
                                              ORDER BY table_name""").fetchall()]
    parts = [f"SELECT {COLUMNS}, 'staging.{t}' AS predicted_in, '{t[-8:]}' AS taken FROM staging.{t}"
             for t in snapshots]
    parts.append(f"SELECT {COLUMNS}, 'main.system_predicted', '99999999' FROM main.system_predicted")
    return snapshots, "\n    UNION ALL ".join(parts)


def load(con):
    before = prepare_table(con, TABLE, SOURCE)
    snapshots, union = sources(con)
    print(f"  predictions read from main.system_predicted and {len(snapshots)} snapshot(s): "
          f"{', '.join(snapshots) or 'none'}")
    con.execute(Template((HERE / "source.sql").read_text(encoding="utf-8")).substitute(sources=union))
    print(f"  transform.prediction_source: {table_count(con, 'transform.prediction_source'):,} prediction(s)")

    run_sql_file(con, transform_file(TABLE))
    inserted, updated = merge_counts(con, HERE / "counts.sql")
    run_sql_file(con, HERE / "load.sql")
    report_merge(TABLE, before, table_count(con, TABLE), inserted, updated, [])

    print(f"\n  {'population':<12}{'revealed by':<12}{'rows':>9}" + "".join(f"{k:>16}" for k in KINDS))
    print(f"  {'':<33}" + "".join(f"{'pred / found':>16}" for _ in KINDS))
    found = ", ".join(f"avg(p_{k}), avg(found_{k}::INTEGER)" for k in KINDS)
    for r in con.execute(f"""SELECT is_catalog, revealed_by, count(*), {found}
                             FROM main.{TABLE} GROUP BY 1, 2 ORDER BY 1 DESC, 2""").fetchall():
        cells = "".join(f"{(r[3 + 2 * i] or 0):>8.1%}/{r[4 + 2 * i]:<7.1%}" for i in range(len(KINDS)))
        print(f"  {'catalogued' if r[0] else 'boxel':<12}{r[1]:<12}{r[2]:>9,}{cells}")
    print("\n  score over 'survey' only: a catalogue hit contains its target by construction.")

    oe = ("bh", "wr", "neutron", "herbig", "otype")
    print(f"\n  found / predicted by region within mass code, 'survey' rows, cells of {MIN_CELL}+ systems")
    print(f"  {'region':<30}{'mc':<4}{'rows':>7}{'sectors':>9}{'largest':>9}" + "".join(f"{k:>9}" for k in oe))
    for r in run_sql_file(con, HERE / "by_region.sql", [MIN_CELL]).fetchall():
        ratios = "".join(f"{'-':>9}" if v is None else f"{v:>8.2f}x" for v in r[5:])
        print(f"  {r[0][:29]:<30}{r[1]:<4}{r[2]:>7,}{r[3]:>9,}{r[4]:>9.0%}{ratios}")
    print("  'largest' is the share of the cell's rows in its biggest sector: a cell one sector"
          " dominates measures that sector, not the region.")
    return table_count(con, TABLE)


def main():
    con = connect(memory_limit="8GB", threads=8)
    try:
        load(con)
    finally:
        con.close()
    print("DONE_LOAD_PREDICTION_OUTCOME")


if __name__ == "__main__":
    from common.runlog import start
    start()
    main()

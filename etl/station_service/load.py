import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (check_references, connect, merge_counts, prepare_table,
                       report_merge, run_sql_file, table_count, transform_file)

HERE = pathlib.Path(__file__).resolve().parent
TABLE = "station_service"
STAGED = "staging.spansh_station_service"


def load(con):
    before = prepare_table(con, TABLE, STAGED)

    run_sql_file(con, transform_file(TABLE))
    n_staged = table_count(con, STAGED)
    n_src = table_count(con, "transform.station_service")
    print(f"transform.station_service: {n_src:,} of {n_staged:,} staged station(s)")
    unresolved = run_sql_file(con, HERE / "unresolved.sql").fetchall()
    if unresolved:
        print(f"  {len(unresolved):,} station(s) left out: their system is not in "
              f"system_known yet. Run etl/system_known/refresh.py, then this.")
        for market_id, name, system, sid in unresolved[:10]:
            print(f"    {market_id:<12}{name[:30]:<31}{system} ({sid})")

    delisted = run_sql_file(con, HERE / "delisted.sql").fetchall()
    inserted, updated = merge_counts(con, HERE / "counts.sql")
    run_sql_file(con, HERE / "load.sql")

    after = table_count(con, TABLE)
    report_merge(TABLE, before, after, inserted, updated, [],
                 extra=f" ({len(delisted):,} of them delisted)")
    if delisted:
        print(f"  {len(delisted):,} station(s) no longer in the pull -- kept, is_listed "
              f"set FALSE:")
        for market_id, name, trader, broker in delisted[:20]:
            print(f"    {market_id:<12}{name[:30]:<31}trader {trader:<13}broker {broker}")

    print("\nreferential integrity:")
    check_references(con, TABLE)

    print(f"\n  {'service':<28}{'listed':>8}{'large pad':>11}{'with UC':>9}")
    for label, where in (("Material Trader: Raw", "material_trader = 'Raw'"),
                         ("Material Trader: Manufactured", "material_trader = 'Manufactured'"),
                         ("Material Trader: Encoded", "material_trader = 'Encoded'"),
                         ("Technology Broker: Human", "technology_broker = 'Human'"),
                         ("Technology Broker: Guardian", "technology_broker = 'Guardian'")):
        n, large, uc = con.execute(f"""
            SELECT count(*), count(*) FILTER (WHERE has_large_pad),
                   count(*) FILTER (WHERE has_universal_cartographics)
            FROM {TABLE} WHERE is_listed AND {where}""").fetchone()
        print(f"  {label:<28}{n:>8,}{large:>11,}{uc:>9,}")
    return after


def main():
    con = connect()
    try:
        load(con)
    finally:
        con.close()
    print("DONE_LOAD_STATION_SERVICE")


if __name__ == "__main__":
    main()

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (check_references, connect, merge_counts, prepare_table,
                       report_merge, run_sql_file, table_count, transform_file)

HERE = pathlib.Path(__file__).resolve().parent
TABLE = "carrier"
STAGED = "staging.edastro_fleet_carrier"

COLONIA = "sqrt(pow(k.x + 9530.5, 2) + pow(k.y + 910.28, 2) + pow(k.z - 19808.13, 2))"
SOL = "sqrt(pow(k.x, 2) + pow(k.y, 2) + pow(k.z, 2))"


def load(con):
    before = prepare_table(con, TABLE, STAGED)

    run_sql_file(con, transform_file(TABLE))
    n_src, n_placed = con.execute("""
        SELECT count(*), count(system_id) FROM transform.carrier""").fetchone()
    print(f"transform.carrier: {n_src:,} carrier(s), {n_placed:,} placed in "
          f"system_known ({n_placed / n_src:.1%})")

    inserted, updated = merge_counts(con, HERE / "counts.sql")
    run_sql_file(con, HERE / "load.sql")

    orphans = [f"{r[0]}  {r[1]}"
               for r in run_sql_file(con, HERE / "orphans.sql").fetchall()[:20]]
    after = table_count(con, TABLE)
    report_merge(TABLE, before, after, inserted, updated, orphans)
    print("  updates on an unchanged feed are EXPECTED: is_reliable is recomputed from\n"
          "  now(), so carriers cross the 365/90-day boundaries between runs.")

    print("\nreferential integrity:")
    check_references(con, TABLE)

    print(f"\n  PARKED (last_moved) vs CONFIRMED (last_seen) -- read them together:\n")
    print(f"  {'last seen':<20}{'total':>10}{'parked 1y+':>13}{'parked 2y+':>13}")
    for r in con.execute(f"""
            SELECT CASE WHEN last_seen > now() - INTERVAL 90 DAY  THEN 'a: within 90 days'
                        WHEN last_seen > now() - INTERVAL 365 DAY THEN 'b: within a year'
                        ELSE 'c: over a year ago' END AS bucket,
                   count(*),
                   count(*) FILTER (WHERE last_moved < now() - INTERVAL 365 DAY),
                   count(*) FILTER (WHERE last_moved < now() - INTERVAL 730 DAY)
            FROM {TABLE} GROUP BY 1 ORDER BY 1""").fetchall():
        print(f"  {r[0][3:]:<20}{r[1]:>10,}{r[2]:>13,}{r[3]:>13,}")

    print(f"\n  WHERE THE RELIABLE ONES ARE (parked 1y+ AND seen in the last 90d):\n")
    print(f"  {'region':<26}{'carriers':>10}{'reliable':>10}{'with UC':>9}")
    for r in con.execute(f"""
            SELECT CASE WHEN {SOL} <= 1000     THEN 'a: bubble (<1k ly)'
                        WHEN {COLONIA} <= 500  THEN 'b: Colonia (2nd hub)'
                        WHEN {SOL} <= 5000     THEN 'c: 1k-5k ly'
                        ELSE 'd: DEEP SPACE' END AS region,
                   count(*), count(*) FILTER (WHERE c.is_reliable),
                   count(*) FILTER (WHERE c.is_reliable
                                      AND c.has_universal_cartographics)
            FROM {TABLE} c JOIN main.system_known k ON k.system_id = c.system_id
            GROUP BY 1 ORDER BY 1""").fetchall():
        print(f"  {r[0][3:]:<26}{r[1]:>10,}{r[2]:>10,}{r[3]:>9,}")

    print(f"\n  DEEP-SPACE NETWORKS (name-inferred, Colonia excluded):")
    for r in con.execute(f"""
            SELECT CASE WHEN upper(coalesce(c.carrier_name, '')) LIKE 'DSSA%'   THEN 'DSSA'
                        WHEN upper(coalesce(c.carrier_name, '')) LIKE '[IGAU]%' THEN '[IGAU]'
                        WHEN upper(coalesce(c.carrier_name, '')) LIKE '[STAR]%' THEN '[STAR]'
                        ELSE 'unaffiliated' END AS network,
                   count(*) FILTER (WHERE c.is_reliable) AS reliable, count(*) AS total
            FROM {TABLE} c JOIN main.system_known k ON k.system_id = c.system_id
            WHERE {SOL} > 5000 AND {COLONIA} > 500
            GROUP BY 1 ORDER BY reliable DESC""").fetchall():
        print(f"    {r[0]:<16}{r[1]:>5} reliable of {r[2]:>5}")
    return after


def main():
    con = connect()
    try:
        load(con)
    finally:
        con.close()
    print("DONE_LOAD_CARRIER")


if __name__ == "__main__":
    main()

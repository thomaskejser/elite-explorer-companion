import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (check_references, connect, merge_counts, prepare_table,
                       report_merge, run_sql_file, table_count, transform_file)

HERE = pathlib.Path(__file__).resolve().parent
TABLE = "system_catalog"
STAGED = "staging.system_catalog_curated"
ALIAS_PASSES = 12
PLACE_HOPS = 8


def _exists(con, schema, table):
    return con.execute("""SELECT count(*) FROM duckdb_tables()
                          WHERE schema_name = ? AND table_name = ?""",
                       [schema, table]).fetchone()[0]


def resolve_by_name(con):
    run_sql_file(con, transform_file("system_catalog_name"))
    resolved, cleared, ambiguous = merge_counts(con, HERE / "name_counts.sql")
    run_sql_file(con, HERE / "name.sql")
    print(f"  by name:  {resolved:,} set, {cleared:,} reset to NULL for recomputation, "
          f"{ambiguous:,} name(s) held by more than one game system left NULL")


def resolve_by_alias(con):
    if not _exists(con, "main", "system_catalog_alias"):
        print("  main.system_catalog_alias does not exist -- identity resolution skipped."
              "\n  Load it first: python etl/system_catalog_alias/refresh.py")
        return
    total = 0
    for rounds in range(1, ALIAS_PASSES + 1):
        run_sql_file(con, transform_file("system_catalog_agreed"))
        moved = table_count(con, "transform.system_catalog_agreed")
        if moved:
            run_sql_file(con, HERE / "alias.sql")
        total += moved
        print(f"    pass {rounds}: {moved:,} resolved via an alias")
        if not moved:
            break
    ambiguous = run_sql_file(con, HERE / "ambiguous.sql").fetchone()[0]
    print(f"  by identity: {total:,} resolved in {rounds} pass(es); {ambiguous:,} name(s) "
          f"left NULL because their neighbours disagree")


def place(con):
    if not _exists(con, "staging", "catalog_parallax"):
        print("  staging.catalog_parallax is absent -- missing_coordinate left as it is.")
        return
    run_sql_file(con, transform_file("system_catalog_placed"))
    placed = table_count(con, "transform.system_catalog_placed")
    for hops in range(1, PLACE_HOPS + 1):
        run_sql_file(con, HERE / "place.sql")
        grown = table_count(con, "transform.system_catalog_placed")
        if grown == placed:
            break
        placed = grown
    run_sql_file(con, transform_file("system_catalog_coordinate"))
    changed = run_sql_file(con, HERE / "coordinate_counts.sql").fetchone()[0]
    run_sql_file(con, HERE / "coordinate.sql")
    missing, have = con.execute(f"""SELECT count(*) FILTER (WHERE missing_coordinate),
                                           count(*) FILTER (WHERE NOT missing_coordinate)
                                    FROM {TABLE}""").fetchone()
    print(f"  missing_coordinate: {placed:,} placeable name(s) after {hops} hop(s); "
          f"{changed:,} row(s) updated; {missing:,} cannot be placed, {have:,} can")


def coverage(con):
    print("\n  COVERAGE -- how much of each real catalogue Frontier shipped:")
    print(f"    {'type':<6}{'catalogue':>12}{'own name':>11}{'rate':>9}"
          f"{'in game':>11}{'rate':>9}")
    rows = run_sql_file(con, HERE / "coverage.sql").fetchall()
    for typ, n, own, got in rows + [("ALL", sum(r[1] for r in rows),
                                     sum(r[2] for r in rows), sum(r[3] for r in rows))]:
        print(f"    {typ:<6}{n:>12,}{own:>11,}{own / max(n, 1):>8.1%}{got:>11,}"
              f"{got / max(n, 1):>8.1%}")


def load(con):
    before = prepare_table(con, TABLE, STAGED)

    run_sql_file(con, transform_file(TABLE))
    print(f"transform.{TABLE}: {table_count(con, f'transform.{TABLE}'):,} row(s)")

    inserted, updated = merge_counts(con, HERE / "counts.sql")
    run_sql_file(con, HERE / "load.sql")
    orphans = [f"{t}: {n:,} name(s)"
               for t, n in run_sql_file(con, HERE / "orphans.sql").fetchall()]
    after = table_count(con, TABLE)
    report_merge(TABLE, before, after, inserted, updated, orphans)

    print("\nresolving system_id...", flush=True)
    resolve_by_name(con)
    resolve_by_alias(con)
    place(con)
    coverage(con)

    print("\nreferential integrity:")
    check_references(con, TABLE)
    return after


def main():
    con = connect()
    try:
        load(con)
    finally:
        con.close()
    print("DONE_LOAD_SYSTEM_CATALOG")


if __name__ == "__main__":
    main()

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (ROOT, merge_counts, prepare_table, report_merge, run_sql_file,
                       table_count)
from common.current import connect

HERE = pathlib.Path(__file__).resolve().parent
TABLE = "route"
SEED = ROOT / "input" / "route.parquet"


def stage(con):
    """Expose input/route.parquet as `src_route` for the merge to read.

    A TEMP VIEW, not a table, and not a `transform` schema: this loader writes to the
    APP-STATE database, which is the one file in this project that cannot be rebuilt, so
    it leaves nothing behind in it. The view lives for this session and the parquet stays
    the authoritative copy -- it is hand-made, and re-solving a route rewrites it.
    """
    con.execute(f"""
        CREATE OR REPLACE TEMP VIEW src_route AS
        SELECT route, hop::INTEGER AS hop, system, x, y, z, hop_ly, to_go_ly,
               is_neutron, boosted_ly, jumps::INTEGER AS jumps
        FROM read_parquet('{SEED.as_posix()}')""")
    return table_count(con, "src_route")


def load(con):
    if not SEED.exists():
        raise SystemExit(f"missing {SEED} -- the route seed is hand-made and there is "
                         f"nothing to derive it from")
    before = prepare_table(con, TABLE, str(SEED))
    n_src = stage(con)
    routes = con.execute("""SELECT route, max(hop), min(boosted_ly)
                            FROM src_route GROUP BY route ORDER BY route""").fetchall()
    print(f"src_route: {n_src:,} row(s) in {len(routes)} route(s)")
    for name, jumps, ly in routes:
        print(f"  {name:<34}{jumps:>4} jump(s) at {ly:,.0f} ly boosted")

    inserted, updated = merge_counts(con, HERE / "counts.sql")
    # *** A DOCUMENTED EXCEPTION TO MERGE-NEVER-DROP, AND THE ONLY ONE HERE. *** Hops are
    # an ORDER, not identities, so re-solving a route renumbers them: a chain that gets
    # shorter would otherwise keep its old tail and offer waypoints it no longer passes,
    # which is worse than offering no route at all. Scoped to routes the seed still
    # names, so a route dropped from the seed is left alone and reported as an orphan.
    stale = run_sql_file(con, HERE / "stale.sql").fetchall()[0][0]
    run_sql_file(con, HERE / "load.sql")

    orphans = [f"{r[0]}  ({r[1]} hops, {r[2]} jumps) -- not in the seed"
               for r in run_sql_file(con, HERE / "orphans.sql").fetchall()]
    after = table_count(con, TABLE)
    report_merge(TABLE, before, after, inserted, updated, orphans,
                 extra=f", {stale} stale hop(s) deleted")

    bad = con.execute(f"""
        SELECT route, hop, system, hop_ly, boosted_ly
        FROM {TABLE} WHERE hop_ly > boosted_ly ORDER BY route, hop""").fetchall()
    for r in bad:
        print(f"  ! {r[0]} hop {r[1]} ({r[2]}) is {r[3]:,.1f} ly, beyond {r[4]:,.0f}")
    gaps = con.execute(f"""
        SELECT route, count(*), max(hop) + 1 FROM {TABLE}
        GROUP BY route HAVING count(*) <> max(hop) + 1""").fetchall()
    for r in gaps:
        print(f"  ! {r[0]} has {r[1]} rows for {r[2]} hops -- the chain has a hole")
    return after


def main():
    con = connect()
    try:
        load(con)
    finally:
        con.close()
    print("DONE_LOAD_ROUTE")


if __name__ == "__main__":
    main()

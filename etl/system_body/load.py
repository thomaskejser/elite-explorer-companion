import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (connect, merge_counts, prepare_table, report_merge,
                       run_sql_file, staged_source, table_count, transform_file)

HERE = pathlib.Path(__file__).resolve().parent
TABLE = "system_body"
ROLES = ("spansh_body", "edsm_celestial_body", "edastro_planet", "edastro_known_rare",
         "edastro_neutron_star")
BUCKETS_FULL, BUCKETS_DELTA, DELTA_MAX = 128, 8, 60_000_000


def provenance(con):
    full = False
    print("  staged sources:")
    for role in ROLES:
        row = staged_source(con, role)
        if not row:
            raise SystemExit(f"    {role} is NOT STAGED -- run etl/system_body/stage.py")
        table, is_delta, at, rows = row
        full = full or (role == "spansh_body" and not is_delta)
        print(f"    {role:<22}staging.{table:<30}{(rows or 0):>14,}  "
              f"{'delta' if is_delta else 'FULL':<6}{at:%Y-%m-%d %H:%M}")
    return full


def live_shape(con):
    cols = {r[0] for r in con.execute("""SELECT column_name FROM duckdb_columns()
                                         WHERE schema_name = 'main' AND table_name = ?""",
                                      [TABLE]).fetchall()}
    if cols and "body_no" not in cols:
        raise SystemExit(f"main.{TABLE} has no body_no column, so it is not the shape "
                         f"schema/{TABLE}.sql declares. The table must be rebuilt from that "
                         f"file (scripts/build_fresh_db.py); this loader does not alter it.")


def buckets_for(con, override):
    if override:
        return override
    staged = con.execute("""SELECT coalesce(sum(row_count), 0) FROM (
                                SELECT role, arg_max(row_count, ingested_at_utc) AS row_count
                                FROM staging.ingest_manifest
                                WHERE role IN ('spansh_body', 'edsm_celestial_body',
                                               'edastro_planet')
                                GROUP BY role)""").fetchone()[0]
    return BUCKETS_DELTA if staged <= DELTA_MAX else BUCKETS_FULL


def merge_buckets(con, buckets, limit):
    run_sql_file(con, transform_file(TABLE))
    inserted = updated = upgraded = 0
    todo = buckets if not limit else min(limit, buckets)
    print(f"\n  merging {todo} of {buckets} bucket(s) (abs((system_id >> 3) % {buckets}))...",
          flush=True)
    for b in range(todo):
        t0 = time.time()
        run_sql_file(con, HERE / "transform.sql", [buckets, b] * 7)
        g = run_sql_file(con, HERE / "upgrade_counts.sql", [buckets, b]).fetchone()[0]
        if g:
            run_sql_file(con, HERE / "upgrade.sql", [buckets, b])
        i, u = run_sql_file(con, HERE / "counts.sql", [buckets, b]).fetchone()
        run_sql_file(con, HERE / "load.sql", [buckets, b])
        inserted += i
        updated += u
        upgraded += g
        if (b + 1) % 8 == 0:
            con.execute("CHECKPOINT")
        if todo <= 16 or (b + 1) % max(1, todo // 8) == 0 or b + 1 == todo:
            print(f"    bucket {b+1:>4}/{todo}   +{i:,} inserted  {u:,} updated  "
                  f"{g:,} index(es) learned   {time.time()-t0:.0f}s", flush=True)
    return inserted, updated, upgraded, todo == buckets


def cascade(con):
    run_sql_file(con, transform_file("system_body_primary"))
    ambiguous = table_count(con, "transform.system_body_primary")
    demoted, promoted = merge_counts(con, HERE / "cascade_counts.sql")
    run_sql_file(con, HERE / "cascade.sql")
    print(f"\n  primary cascade: {ambiguous:,} staged system(s) name >1 primary; "
          f"{demoted:,} demoted, {promoted:,} promoted")
    systems, rows = merge_counts(con, HERE / "sweep_counts.sql")
    if systems:
        run_sql_file(con, HERE / "sweep.sql")
    print(f"  global sweep: {systems:,} system(s) held >1 primary, {rows:,} row(s) demoted")
    return demoted + promoted + rows


def report(con):
    total, typed, primary, disc, catalogue, unknown = con.execute(f"""
        SELECT count(*), count(body_id), count(*) FILTER (WHERE is_primary),
               count(discovered_time),
               count(*) FILTER (WHERE source IN ('edastro_rare', 'edastro_neutron')),
               count(*) FILTER (WHERE body_no = -1)
        FROM {TABLE}""").fetchone()
    print(f"\n  {'rows':<34}{total:>14,}")
    for label, n in (("body type known", typed), ("is_primary", primary),
                     ("discovered_time", disc), ("CATALOGUE-ONLY (not a scan)", catalogue),
                     ("body_no unknown (-1)", unknown)):
        print(f"  {label:<34}{n:>14,}{100.0*n/max(total,1):>7.2f}%")
    dual, mismatch = con.execute(f"""
        SELECT (SELECT count(*) FROM (SELECT system_id FROM {TABLE} WHERE is_primary
                                      GROUP BY 1 HAVING count(*) > 1)),
               (SELECT count(*) FROM {TABLE} sb JOIN main.system_known sk USING (system_id)
                WHERE sb.is_primary AND sk.primary_star_body_id IS NOT NULL
                  AND sb.body_id IS DISTINCT FROM sk.primary_star_body_id)""").fetchone()
    print(f"\n  systems with >1 is_primary row      {dual:>12,}  "
          f"{'<== BROKEN' if dual else '(ok)'}")
    print(f"  is_primary disagrees with system_known.primary_star_body_id  {mismatch:>12,}")


def load(con, buckets=None, limit=None):
    live_shape(con)
    if not table_count(con, "main.system_known"):
        raise SystemExit("main.system_known is empty -- run etl/system_known/refresh.py")
    full = provenance(con)
    before = prepare_table(con, TABLE, "transform.system_body")

    print("\n  resolving the rare-star catalogue by name...", flush=True)
    run_sql_file(con, transform_file("system_body_rare"))
    print(f"    transform.system_body_rare: "
          f"{table_count(con, 'transform.system_body_rare'):,} row(s)")

    n = buckets_for(con, buckets)
    inserted, updated, upgraded, complete = merge_buckets(con, n, limit)
    cascaded = cascade(con) if complete else 0
    if not complete:
        print("\n  --limit: primary cascade skipped until every bucket is merged")

    orphans = (run_sql_file(con, HERE / "orphans.sql").fetchall()
               if full and complete else [])
    after = table_count(con, TABLE)
    report_merge(TABLE, before, after, inserted, updated, orphans,
                 extra=f", {upgraded:,} body_no -1 given a real index, "
                       f"{cascaded:,} primary flag(s) moved")
    if not full:
        print("  orphans NOT reported: the Spansh window is a delta, so a body it does "
              "not carry is a body that did not change.")
    report(con)
    return after


def _arg(flag, default=None):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


def main():
    buckets = _arg("--buckets")
    limit = _arg("--limit")
    con = connect(memory_limit="6GB", threads=8)
    try:
        load(con, int(buckets) if buckets else None, int(limit) if limit else None)
    finally:
        con.close()
    print("DONE_LOAD_SYSTEM_BODY")


if __name__ == "__main__":
    main()

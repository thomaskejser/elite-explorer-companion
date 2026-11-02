import datetime
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (check_references, connect, merge_counts, prepare_table,
                       report_merge, run_sql_file, staged_source, staging_file,
                       table_count, transform_file)

HERE = pathlib.Path(__file__).resolve().parent
TABLE = "system_known"
ROLES = ("spansh_system", "spansh_body", "edsm_star_system", "edastro_star_system")
ROWS_PER_BATCH = 4_000_000
SHAPE_BUCKETS, SHAPE_MAX = 16, 5_000_000
KNN_LABELS = 2_000_000


def provenance(con):
    widest = False
    print("  staged sources:")
    for role in ROLES:
        row = staged_source(con, role)
        if not row:
            print(f"    {role:<22}NOT STAGED -- run etl/system_known/stage.py")
            continue
        table, is_delta, at, rows = row
        widest = widest or not is_delta
        print(f"    {role:<22}staging.{table:<32}{(rows or 0):>14,}  "
              f"{'delta' if is_delta else 'FULL':<6}{at:%Y-%m-%d %H:%M}")
    return widest


def fill_region(con):
    n = con.execute("""SELECT count(*) FROM transform.system_known
                       WHERE region_id IS NULL""").fetchone()[0]
    if not n:
        return 0
    import numpy as np
    from scipy.spatial import cKDTree
    lab = con.execute(f"""SELECT region_id, x, y, z FROM main.system_known
                          WHERE region_id IS NOT NULL
                          USING SAMPLE {KNN_LABELS} ROWS""").df()
    if lab.empty:
        print(f"    {n:,} system(s) have no region and main.system_known has no labels "
              f"to vote with -- left NULL")
        return 0
    pts = con.execute("""SELECT system_id, x, y, z FROM transform.system_known
                         WHERE region_id IS NULL""").df()
    tree = cKDTree(lab[["x", "y", "z"]].to_numpy())
    _, idx = tree.query(pts[["x", "y", "z"]].to_numpy(), k=5, workers=-1)
    votes = lab["region_id"].to_numpy()[idx]
    pred = np.array([np.bincount(v).argmax() for v in votes], dtype=np.int64)
    con.register("_knn", pts[["system_id"]].assign(region_id=pred))
    con.execute("""UPDATE transform.system_known SET region_id = k.region_id
                   FROM _knn k WHERE transform.system_known.system_id = k.system_id""")
    con.unregister("_knn")
    print(f"    {n:,} region(s) filled by nearest neighbour over {len(lab):,} labels")
    return n


def build_transform(con, buckets=None):
    print("\n  defining transform.system_known...", flush=True)
    run_sql_file(con, transform_file(TABLE))

    print("  reducing the body dump to one arrival star per system...", flush=True)
    t0 = time.time()
    run_sql_file(con, staging_file("primary_star"))
    print(f"    staging.primary_star: {table_count(con, 'staging.primary_star'):,} "
          f"row(s) in {time.time()-t0:.0f}s", flush=True)

    buckets = buckets or shape_buckets(con)
    print(f"  shaping in {buckets} bucket(s)...", flush=True)
    for b in range(buckets):
        t0 = time.time()
        run_sql_file(con, HERE / "transform.sql", [buckets, b] * 4)
        if buckets == 1 or (b + 1) % max(1, buckets // 8) == 0:
            n = table_count(con, "transform.system_known_source")
            print(f"    bucket {b+1:>3}/{buckets}   {n:,} rows   {time.time()-t0:.0f}s",
                  flush=True)

    for b in range(buckets):
        run_sql_file(con, HERE / "promote.sql", [buckets, b])
    staged = table_count(con, "transform.system_known")
    print(f"  transform.system_known: {staged:,} row(s)")
    return staged


def shape_buckets(con):
    rows = [staged_source(con, r) for r in
            ("spansh_system", "edsm_star_system", "edastro_star_system")]
    widest = max((r[3] or 0) for r in rows if r)
    return 1 if widest <= SHAPE_MAX else SHAPE_BUCKETS


def sector_batches(con, rows_per_batch=ROWS_PER_BATCH):
    rows = run_sql_file(con, HERE / "batches.sql").fetchall()
    if not rows:
        return []
    batches, lo, run = [], rows[0][0], 0
    for sector_id, n in rows:
        run += n
        if run >= rows_per_batch:
            batches.append((lo, sector_id + 1))
            lo, run = sector_id + 1, 0
    if run:
        batches.append((lo, rows[-1][0] + 1))
    return batches


def load(con, rows_per_batch=None, shape=True):
    at = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    before = prepare_table(con, TABLE, "transform.system_known")
    full = provenance(con)

    if shape:
        staged = build_transform(con)
    else:
        staged = table_count(con, "transform.system_known")
        print(f"  transform.system_known: {staged:,} row(s), shaped already")

    skipped = run_sql_file(con, HERE / "skipped.sql").fetchall()
    if skipped:
        total = con.execute("""SELECT count(*) FROM transform.system_known_source
                               WHERE sector_id IS NULL""").fetchone()[0]
        print(f"  *** {total:,} procedural system(s) EXCLUDED -- their sector is not in "
              f"`sector` yet. Run etl/sector/refresh.py, then re-run this.")
        for name, n in skipped:
            print(f"      {name:<40}{n:>12,}")

    fill_region(con)

    for label, w in (("coordinates", "x IS NOT NULL"),
                     ("region", "region_id IS NOT NULL"),
                     ("arrival star", "primary_star_body_id IS NOT NULL"),
                     ("body_count", "body_count IS NOT NULL"),
                     ("hand-named (sector 0)", "sector_id = 0")):
        c = con.execute(f"SELECT count(*) FROM transform.system_known "
                        f"WHERE {w}").fetchone()[0]
        print(f"    {label:<26}{c:>14,}{100.0*c/max(staged,1):>7.2f}%")

    inserted, updated = merge_counts(con, HERE / "counts.sql")
    batches = sector_batches(con, rows_per_batch or ROWS_PER_BATCH)
    print(f"\n  merging {len(batches)} sector batch(es), first_seen = {at}...",
          flush=True)
    for i, (lo, hi) in enumerate(batches, 1):
        run_sql_file(con, HERE / "load.sql", [lo, hi, at])
        if i % 8 == 0:
            con.execute("CHECKPOINT")
        if i % max(1, len(batches) // 8) == 0 or i == len(batches):
            print(f"    sectors {lo:>7}..{hi:<7} {i:>3}/{len(batches)}   "
                  f"{table_count(con, TABLE):,} rows", flush=True)

    orphans = run_sql_file(con, HERE / "orphans.sql").fetchall() if full else []
    after = table_count(con, TABLE)
    report_merge(TABLE, before, after, inserted, updated, orphans)
    if not full:
        print("  orphans NOT reported: every staged source is a delta, so a row this "
              "load did not see is a system that did not change.")

    print("\n  references:")
    check_references(con, TABLE)
    return after


def main():
    con = connect(memory_limit="4GB", threads=8)
    try:
        load(con)
    finally:
        con.close()
    print("DONE_LOAD_SYSTEM_KNOWN")


if __name__ == "__main__":
    from common.runlog import start
    start()
    main()

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
    """Print which physical table each role resolves to, and how wide it is.

    The staging table is named after the download and the role is a view over it, so
    nothing in the merge SQL says which window is being merged. This is where it gets
    said. `full` in a name means the catalogue; anything else is a delta and the load
    that follows can only ever ADD.
    """
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
    """Give a region to systems whose sector cannot supply one.

    Only hand-named systems reach this: a procedural name resolves its sector, and the
    sector carries the region. There is no formula -- region is a hand-drawn volume --
    so it is a nearest-neighbour vote against systems that already have one, which is
    the only reason this step is Python and not a .sql file.

    The labels come from main.system_known rather than from a feed, so the answer does
    not change with the window that happens to be staged.
    """
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
    """Shape the staged feeds into transform.system_known, one bucket at a time.

    The three feeds are 292M rows for a full stage and reducing them to one row per
    system in a single statement needs a hash table over 200M groups -- the operating
    system killed a run that tried. Each bucket takes hash(system_id) %% n of every
    source, so the aggregate stays a few million groups wide and spills instead of
    growing. A delta is small enough to do in one pass and does.
    """
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
    """One pass for a delta, SHAPE_BUCKETS for anything catalogue-sized.

    Decided on the row count of the widest staged feed rather than on the window name,
    because what costs memory is how many groups the aggregate holds and nothing else.
    """
    rows = [staged_source(con, r) for r in
            ("spansh_system", "edsm_star_system", "edastro_star_system")]
    widest = max((r[3] or 0) for r in rows if r)
    return 1 if widest <= SHAPE_MAX else SHAPE_BUCKETS


def sector_batches(con, rows_per_batch=ROWS_PER_BATCH):
    """Split the staged sectors into [lo, hi) sector_id ranges of ~equal ROW COUNT.

    Batching on sector rather than on a hash of the id does two things a hash cannot.
    The target is written in sector order, so each row group ends up with a tight
    sector_id range in its statistics and a filter on sector can skip whole row groups --
    the same propagation that eliminates union legs. And a sector boundary is a
    MEANINGFUL resume point: "merged through sector X" stays true if the batch size
    changes, where "bucket 37 of 64" does not.

    The batches are cut on a running row count, never on a fixed number of sectors:
    the 12,100 sectors differ by orders of magnitude and sector_id 0 alone holds every
    hand-named system.
    """
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
    at = datetime.datetime.now().replace(microsecond=0)
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
    main()

"""SEED input/region.parquet -- the authoritative list of galactic regions.

ONE-TIME SEEDER. Writes only the PARQUET, and only if it does not already exist; it
never touches the `region` table (that is etl/load_region.py). There is deliberately
no --force: once seeded, input/region.parquet is the ONLY source of truth for regions
and is MAINTAINED BY HAND. Nothing re-derives it. If it is wrong, edit it.

That is a real difference from every other table here: `region` has no upstream feed.
The 42 regions are hand-drawn by Frontier, are not derivable from a system's name or
coordinates by any formula, and change only when Frontier changes them.

Names are extracted once, from canonn_codex_event, which carries region_name (an
internal token holding the id) alongside region_name_localised (the display name).
Two things make that extraction non-trivial and are worth knowing if you ever reseed:

  * region_id is the GAME'S OWN id, parsed out of the region_name token -- NOT a
    sequence we invented. That matters: input/region.parquet already keys 545,485
    labelled points on these ids, and the codex feed uses them. Inventing our own
    would orphan all of it.
  * the codex is uploaded by clients in every language, so a naive pick returns
    "Bras Ecu-Croix externe" instead of "Outer Scutum-Centaurus Arm". We take the
    MODAL non-null localised name per id, English being the plurality.

Usage:  python etl/build_region.py     # refuses if input/region.parquet exists
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common.db import ROOT, INPUT, connect

OUT = INPUT / "region.parquet"

# No --force by design: this file is hand-maintained and regenerating would discard
# edits. A deliberate reseed means deleting the file first.
if OUT.exists():
    sys.exit(f"{OUT} already exists and is AUTHORITATIVE (hand-maintained) -- "
             f"refusing to overwrite.\nTo apply it:  python etl/load_region.py\n"
             f"If it is wrong, edit it by hand. For a genuine fresh seed, delete it "
             f"first.")

con = connect(read_only=True)

print("extracting regions from canonn_codex_event...", flush=True)
con.execute("""
CREATE OR REPLACE TEMP TABLE seed AS
WITH c AS (
  SELECT CAST(regexp_extract(region_name, '([0-9]+)', 1) AS BIGINT) AS region_id,
         region_name_localised                                      AS region,
         count(*)                                                   AS n
  FROM canonn_codex_event
  WHERE region_name IS NOT NULL AND region_name_localised IS NOT NULL
  GROUP BY 1, 2
),
ranked AS (
  SELECT *, row_number() OVER (PARTITION BY region_id ORDER BY n DESC) AS rk FROM c
)
SELECT region_id, region FROM ranked WHERE rk = 1
""")

n = con.execute("SELECT count(*) FROM seed").fetchone()[0]
rng = con.execute("SELECT min(region_id), max(region_id) FROM seed").fetchone()
print(f"  {n} region(s), ids {rng[0]}..{rng[1]}")
if n != 42:
    print(f"  ! expected 42 hand-drawn regions, got {n} -- check before trusting this")

# Sanity: every region a labelled system claims must have a name, or the app would
# fall back to "Region <id>" for it.
orphan = con.execute("""
SELECT DISTINCT CAST(region AS BIGINT) rid FROM edastro_star_system
WHERE region IS NOT NULL
  AND CAST(region AS BIGINT) NOT IN (SELECT region_id FROM seed)
ORDER BY 1""").fetchall()
print(f"  region ids used by labelled systems but unnamed: "
      f"{[r[0] for r in orphan] if orphan else 'none'}")

INPUT.mkdir(exist_ok=True)
con.execute(f"""COPY (SELECT region_id, region FROM seed ORDER BY region_id)
                TO '{OUT.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)""")
back = con.execute(f"""SELECT count(*), count(DISTINCT region_id)
                       FROM '{OUT.as_posix()}'""").fetchone()
print(f"\nwrote {OUT}  ({back[0]} rows, {OUT.stat().st_size:,} bytes)")
print(f"  read back: {back[1]} distinct region_id")
same = con.execute(f"""SELECT count(*) FROM (
    SELECT region_id, region FROM seed
    EXCEPT SELECT region_id, region FROM '{OUT.as_posix()}')""").fetchone()[0]
print(f"  round-trips identical: {same == 0}")

print(f"\n  {'id':>4}  region")
for r in con.execute(f"""SELECT region_id, region FROM '{OUT.as_posix()}'
                         ORDER BY region_id""").fetchall():
    print(f"  {r[0]:>4}  {r[1]}")

con.close()
print("\nNOTE the `region` table was NOT touched. Merge with:"
      "\n  python etl/load_region.py")
print("\nDONE_BUILD_REGION")

"""Build `sector` -- one row per unique procedural sector, with a bounding ball.

DERIVED table (see ETL.md): computed from staging.spansh_system, so there is no
input/ file and
no load_sector.py yet. Merge semantics all the same -- created IF NOT EXISTS,
upserted on the natural key `sector`, never dropped, sector_id never renumbered.

  sector_id  BIGINT PRIMARY KEY, plain sequence number, the key other tables carry.
             STABLE: existing sectors keep their id, only new names get one (max+1).
             *** sector_id 0 is the SENTINEL 'crafted' row *** -- not a real sector, but
             something for hand-named systems (Sol, Colonia) to point at, since a NULL
             foreign key cannot take part in a UNIQUE or PRIMARY KEY. Exclude
             sector_id = 0 from any analysis of real sectors.
  sector     the sector name alone, e.g. 'Blae Hypue'. Parsed from procedural system
             names by stripping the ' AB-C d1-234' suffix, so it excludes
             hand-authored systems (Sol, Colonia) which have no sector.
  x, y, z    centre of the sector: the MIDPOINT OF THE BOUNDING BOX of the systems
             we know about. Not the centroid -- avg(x) is dragged toward whichever
             corner people happened to explore, which inflates the radius by ~8% on
             average and up to 2907 ly in the worst case. Not the lattice cell
             centre either, because a few sector NAMES span more than one cell and
             so have no single cell.
  region_id  which of the 42 galactic regions this sector sits in. ONE region for the
             whole sector -- an approximation, 95.0% accurate per held-out test, taken
             because it costs 12,064 lookups instead of 197.6M. No FK: DuckDB cannot
             ALTER one in and system_known already points here.
  is_crafted TRUE for hand-crafted (real-world) sectors, FALSE for procedurally
             generated ones. Derived from the name: crafted sectors all end in
             ' Sector' or ' Dark Region'. 423 of 12,064.
  radius     rough radius: the max TAXICAB (L1) distance from (x,y,z) to any system
             we know about in the sector. Sample-based and therefore a LOWER BOUND
             on the true extent -- a barely-visited sector reports a small radius
             because we have not seen its corners, not because it is small.

Usage:  python etl/build_sector.py
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common.db import (count_then_update, ROOT, connect, has_primary_key, report_merge,
                       comment_file, apply_comment_file)

HERE = pathlib.Path(__file__).resolve().parent

TABLE = "sector"
# sector_id 0: the "no sector" sentinel that hand-named systems point at.
SENTINEL = "crafted"
# sector prefix of a procedural system name, for the region mapping
PROC_SECTOR = r"^(.*) [A-Z][A-Z]-[A-Z] [a-h]([0-9]+-)?[0-9]+$"
# 1280-ly lattice, verified against our own data. A single cell's maximum taxicab
# half-extent is 3 * 640 = 1920, which is the yardstick the diagnostics use.
SECTOR_LY = 1280.0
CELL_MAX_TAXICAB = 3 * SECTOR_LY / 2

con = connect()
con.execute("CREATE SCHEMA IF NOT EXISTS staging")

# DDL comes from schema/<table>.sql, the ONE definition of this table's shape and
# its comments. The model is created with the database and never altered after,
# so this is CREATE TABLE IF NOT EXISTS -- a no-op on an existing database.
con.execute(comment_file(TABLE).read_text(encoding='utf-8'))
before = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
print(f"{TABLE}: {before} existing row(s)")

# Additive migration for a table built before is_crafted existed (ETL.md: never drop).

print("extracting sectors from procedural system names...", flush=True)
con.execute(r"""
CREATE OR REPLACE TEMP TABLE psys AS
-- staging.spansh_system, NOT sys_feat. Verified row-for-row identical on every
-- column used here: same 194,696,927 id64s, and 0 rows where name/x/y/z/
-- declared_body_count differ. sys_feat was spansh_system plus DERIVED columns
-- (mass_code, r_sgra/plane_r/height, is_scanned, has_bh/has_wr/has_neutron),
-- none of which this query touches -- and all of which the new model now
-- reproduces from system_known and system_body JOIN body.
SELECT regexp_extract(name, '^(.*) [A-Z][A-Z]-[A-Z] [a-h]', 1) AS sector, x, y, z
FROM staging.spansh_system
WHERE regexp_matches(name, '^.* [A-Z][A-Z]-[A-Z] [a-h]([0-9]+-)?[0-9]+$')
  AND x IS NOT NULL AND y IS NOT NULL AND z IS NOT NULL
""")

# Two passes: the centre must exist before the radius can be measured from it.
print("computing bounding-box centres...", flush=True)
con.execute("""
CREATE OR REPLACE TEMP TABLE ctr AS
SELECT sector, count(*) AS n,
       (min(x) + max(x)) / 2 AS x,
       (min(y) + max(y)) / 2 AS y,
       (min(z) + max(z)) / 2 AS z
FROM psys GROUP BY 1
""")
print("measuring taxicab radii...", flush=True)
con.execute("""
CREATE OR REPLACE TEMP TABLE fresh AS
SELECT c.sector, c.n, c.x, c.y, c.z,
       max(abs(p.x - c.x) + abs(p.y - c.y) + abs(p.z - c.z)) AS radius,
       -- Hand-crafted sectors are the real-world regions, and they are identifiable
       -- purely from the name: every one ends in ' Sector' (406, e.g. Witch Head
       -- Sector, NGC 2546 Sector) or ' Dark Region' (17, e.g. Coalsack Dark Region).
       -- Verified exhaustive: no procedural name has 3+ words, and the only 9 with a
       -- digit are far-side procgen (Bleia1..5, Praei1..4), not crafted.
       (c.sector LIKE '% Sector' OR c.sector LIKE '% Dark Region') AS is_crafted
FROM ctr c JOIN psys p USING(sector)
GROUP BY 1, 2, 3, 4, 5
""")
n_fresh = con.execute("SELECT count(*) FROM fresh").fetchone()[0]
print(f"  {n_fresh:,} sector(s) measured")

# --- stable id allocation ----------------------------------------------------
# Alphabetical only for the first build's readability; ids are permanent after that.
con.execute(f"""
CREATE OR REPLACE TEMP TABLE newrows AS
SELECT (SELECT coalesce(max(sector_id), 0) FROM {TABLE})
         + row_number() OVER (ORDER BY f.sector) AS sector_id,
       f.sector, f.x, f.y, f.z, f.radius, f.is_crafted
FROM fresh f
WHERE NOT EXISTS (SELECT 1 FROM {TABLE} t WHERE t.sector = f.sector)
""")
ins = con.execute(f"""
INSERT INTO {TABLE} (sector_id, sector, x, y, z, radius, is_crafted)
SELECT sector_id, sector, x, y, z, radius, is_crafted FROM newrows
RETURNING sector_id""").fetchall()

# Geometry moves as coverage grows, so matched rows are updated -- but never the id.
W = f"""WHERE {TABLE}.sector = f.sector
  AND ({TABLE}.x IS DISTINCT FROM f.x OR {TABLE}.y IS DISTINCT FROM f.y
       OR {TABLE}.z IS DISTINCT FROM f.z OR {TABLE}.radius IS DISTINCT FROM f.radius
       OR {TABLE}.is_crafted IS DISTINCT FROM f.is_crafted)"""
upd = count_then_update(con,
    f"SELECT count(*) FROM {TABLE}, fresh f {W}",
    f"""UPDATE {TABLE} SET x = f.x, y = f.y, z = f.z, radius = f.radius,
                          is_crafted = f.is_crafted FROM fresh f {W}""")

# SENTINEL row 0. Hand-named systems (Sol, Colonia) have no sector, and a NULL FK
# cannot participate in a UNIQUE/PRIMARY KEY -- so system_known points them at
# sector_id = 0 instead of NULL. It is NOT a place: coordinates and radius are zero.
# Upserted explicitly because it can never appear in `fresh`, which is derived from
# procedural system names.
sent = con.execute(f"""
INSERT INTO {TABLE} (sector_id, sector, x, y, z, radius, is_crafted)
SELECT 0, '{SENTINEL}', 0, 0, 0, 0, true
WHERE NOT EXISTS (SELECT 1 FROM {TABLE} WHERE sector_id = 0)
RETURNING sector_id""").fetchall()
if sent:
    print(f"  INSERT sentinel sector_id=0 '{SENTINEL}' (for systems with no sector)")

# The sentinel is never in `fresh`, so it must be excluded or it reports as an orphan
# on every single run.
orphan = con.execute(f"""SELECT sector_id, sector FROM {TABLE} t
    WHERE t.sector_id <> 0
      AND NOT EXISTS (SELECT 1 FROM fresh f WHERE f.sector = t.sector)
    ORDER BY sector_id""").fetchall()

after = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
report_merge(TABLE, before, after, len(ins), upd, orphan)

# --------------------------------------------------------------- region_id ---
# One region per SECTOR. Regions are galaxy-scale and sectors are 1280 ly, so a sector
# sits wholly inside one region far more often than not -- measured 95.0% accurate on a
# held-out half of EDAstro's labels, against 99.4% for per-system kNN. That is the trade
# we are taking: 12,064 lookups instead of 197,562,522.
#
# NO FOREIGN KEY on this column, and not by choice: DuckDB has no ALTER TABLE ADD FOREIGN
# KEY, this table is populated, and system_known already has an inbound FK to it -- so
# rebuilding sector to gain the constraint would break that. Referential integrity here is
# the loader's job (region_id always comes from the region table).

print("assigning one region per sector...", flush=True)
import numpy as np
from scipy.spatial import cKDTree

lab = con.execute("""
SELECT CAST(e.region AS INTEGER) AS region_id, s.x, s.y, s.z
FROM edastro_star_system e JOIN spansh_system s ON s.name = e.name
WHERE e.region IS NOT NULL AND s.x IS NOT NULL""").df()

# Two sources, best first:
#   (a) the modal region of the sector's OWN labelled member systems -- direct evidence;
#   (b) k=5 majority around the sector CENTRE -- for the ~2/3 of sectors that contain no
#       labelled system at all, which is why (a) alone is not enough.
con.execute(f"""
CREATE OR REPLACE TABLE staging.sector_region_member AS
SELECT nullif(regexp_extract(e.name, '{PROC_SECTOR}', 1), '') AS sector,
       mode(CAST(e.region AS INTEGER))                        AS region_id,
       count(*)                                               AS labelled
FROM edastro_star_system e
WHERE e.region IS NOT NULL
  AND regexp_matches(e.name, '{PROC_SECTOR}')
GROUP BY 1""")
have = con.execute("""SELECT count(*) FROM staging.sector_region_member m
                      WHERE EXISTS (SELECT 1 FROM sector s WHERE s.sector = m.sector)
                   """).fetchone()[0]
nsec = con.execute(f"SELECT count(*) FROM {TABLE} WHERE sector_id <> 0").fetchone()[0]
print(f"  {have:,} of {nsec:,} sectors contain at least one labelled system")

ctr = con.execute(f"""SELECT sector_id, x, y, z FROM {TABLE}
                      WHERE sector_id <> 0""").df()
tree = cKDTree(lab[["x", "y", "z"]].to_numpy())
_, idx = tree.query(ctr[["x", "y", "z"]].to_numpy(), k=5, workers=-1)
votes = lab["region_id"].to_numpy()[idx]
centre = np.array([np.bincount(v).argmax() for v in votes], dtype=np.int64)
con.register("_ctr", ctr[["sector_id"]].assign(region_id=centre))
con.execute("CREATE OR REPLACE TABLE staging.sector_region_centre AS "
            "SELECT * FROM _ctr")
print(f"  centre kNN covered all {len(centre):,} sectors (fallback)")

# Resolve to ONE row per sector_id FIRST. An UPDATE whose FROM clause reads the table
# being updated (even in a correlated subquery) makes DuckDB treat it as a key rewrite,
# which its foreign-key checker then blocks because system_known references sector.
con.execute(f"""
CREATE OR REPLACE TABLE staging.sector_region AS
SELECT c.sector_id,
       coalesce(m.region_id, c.region_id) AS region_id,
       m.region_id IS NOT NULL            AS from_members
FROM staging.sector_region_centre c
JOIN {TABLE} sc ON sc.sector_id = c.sector_id
LEFT JOIN staging.sector_region_member m ON m.sector = sc.sector""")
src = con.execute("""SELECT count(*) FILTER (WHERE from_members), count(*)
                     FROM staging.sector_region""").fetchone()
print(f"  resolved {src[1]:,} sectors: {src[0]:,} from member systems, "
      f"{src[1]-src[0]:,} from centre kNN")

PRED = f"""FROM staging.sector_region r
WHERE {TABLE}.sector_id = r.sector_id
  AND {TABLE}.region_id IS DISTINCT FROM r.region_id"""
nrup = count_then_update(con,
    f"SELECT count(*) FROM {TABLE} " + PRED.replace("FROM staging", ", staging", 1)
      .replace(f"{TABLE}.sector_id = r.sector_id", f"{TABLE}.sector_id = r.sector_id"),
    f"UPDATE {TABLE} SET region_id = r.region_id " + PRED)
print(f"  set region_id on {nrup:,} sector(s)")

rc = con.execute(f"""SELECT count(*) FILTER (WHERE region_id IS NOT NULL), count(*)
                     FROM {TABLE} WHERE sector_id <> 0""").fetchone()
print(f"  region_id populated: {rc[0]:,}/{rc[1]:,} real sectors")
bad = con.execute(f"""SELECT count(*) FROM {TABLE} k
    WHERE k.region_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM region r WHERE r.region_id = k.region_id)
                   """).fetchone()[0]
print(f"  region_id values not present in `region`: {bad}  "
      f"{'<== BROKEN' if bad else '(clean, though unenforced)'}")

# DDL + comment text (table + every column) live in schema/sector.sql per ETL.md,
# and is re-asserted here because a schema change silently drops comments.
apply_comment_file(con, comment_file(TABLE))

pk = has_primary_key(con, TABLE)
print(f"  {pk or 'NO PRIMARY KEY'}")

# schema_name='main' matters: duckdb_columns() also lists the norm.* views, and
# norm.body would otherwise be counted alongside main.body.
ncc = con.execute("""SELECT count(*) FILTER (WHERE comment IS NOT NULL), count(*)
     FROM duckdb_columns() WHERE schema_name = 'main' AND table_name = ?""",
     [TABLE]).fetchone()
print(f"  column comments: {ncc[0]}/{ncc[1]}"
      + ("" if ncc[0] == ncc[1] else "   <== INCOMPLETE, see ETL.md"))

print(f"\n  {'sector kind':<28}{'sectors':>9}{'mean radius':>13}")
for lab, w in (("hand-crafted", "is_crafted"), ("procedural", "NOT is_crafted")):
    # sector_id <> 0 throughout: the sentinel is not a real sector and would otherwise
    # inflate the crafted count from 423 to 424 and drag its mean radius toward zero.
    c = con.execute(f"SELECT count(*), avg(radius) FROM {TABLE} "
                    f"WHERE {w} AND sector_id <> 0").fetchone()
    print(f"  {lab:<28}{c[0]:>9,}{c[1]:>13.1f}")

print(f"\n  {'radius distribution':<28}{'sectors':>9}")
for lab, lo, hi in (("< 500", 0, 500), ("500-1000", 500, 1000),
                    ("1000-1500", 1000, 1500), ("1500-1920", 1500, 1920),
                    ("> 1920 (multi-cell)", 1920, 1e9)):
    c = con.execute(f"SELECT count(*) FROM {TABLE} "
                    f"WHERE radius >= {lo} AND radius < {hi} "
                    f"AND sector_id <> 0").fetchone()[0]
    print(f"  {lab:<28}{c:>9,}")

print(f"\n  largest radii -- these should be the well-sampled or multi-cell sectors:")
print(f"  {'sector':<30}{'radius':>10}{'x':>10}{'y':>10}{'z':>10}")
for r in con.execute(f"""SELECT sector, radius, x, y, z FROM {TABLE}
                         WHERE sector_id <> 0
                         ORDER BY radius DESC LIMIT 6""").fetchall():
    print(f"  {r[0][:29]:<30}{r[1]:>10.1f}{r[2]:>10.0f}{r[3]:>10.0f}{r[4]:>10.0f}")

print(f"\n  first rows by id:")
print(f"  {'id':>6}  {'sector':<30}{'radius':>10}{'x':>10}{'y':>10}{'z':>10}")
for r in con.execute(f"""SELECT sector_id, sector, radius, x, y, z FROM {TABLE}
                         ORDER BY sector_id LIMIT 5""").fetchall():
    print(f"  {r[0]:>6}  {r[1][:29]:<30}{r[2]:>10.1f}{r[3]:>10.0f}{r[4]:>10.0f}{r[5]:>10.0f}")
con.close()
print("\nDONE_BUILD_SECTOR")

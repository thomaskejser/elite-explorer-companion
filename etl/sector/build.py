import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (apply_comment_file, comment_file, connect, count_then_update,
                       has_primary_key, prepare_table, report_merge, table_count)

HERE = pathlib.Path(__file__).resolve().parent

TABLE = "sector"
SENTINEL = "crafted"
PROC_SECTOR = r"^(.*) [A-Z][A-Z]-[A-Z] [a-h]([0-9]+-)?[0-9]+$"
SECTOR_LY = 1280.0
CELL_MAX_TAXICAB = 3 * SECTOR_LY / 2

con = connect()
con.execute("CREATE SCHEMA IF NOT EXISTS staging")

before = prepare_table(con, TABLE)

print("extracting sectors from procedural system names...", flush=True)
con.execute(r"""
CREATE OR REPLACE TEMP TABLE psys AS
SELECT sector, x, y, z FROM (
    SELECT regexp_extract(name, '^(.*) [A-Z][A-Z]-[A-Z] [a-h]', 1) AS sector,
           name, x, y, z
    FROM staging.spansh_system
    UNION ALL
    SELECT regexp_extract(name, '^(.*) [A-Z][A-Z]-[A-Z] [a-h]', 1), name,
           coords.x, coords.y, coords.z
    FROM staging.edsm_star_system
    UNION ALL
    SELECT regexp_extract(name, '^(.*) [A-Z][A-Z]-[A-Z] [a-h]', 1), name,
           coords.x, coords.y, coords.z
    FROM staging.edastro_star_system
)
WHERE regexp_matches(name, '^.* [A-Z][A-Z]-[A-Z] [a-h]([0-9]+-)?[0-9]+$')
  AND x IS NOT NULL AND y IS NOT NULL AND z IS NOT NULL
""")

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
       (c.sector LIKE '% Sector' OR c.sector LIKE '% Dark Region') AS is_crafted
FROM ctr c JOIN psys p USING(sector)
GROUP BY 1, 2, 3, 4, 5
""")
n_fresh = table_count(con, 'fresh')
print(f"  {n_fresh:,} sector(s) measured")

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

W = f"""WHERE {TABLE}.sector = f.sector
  AND ({TABLE}.x IS DISTINCT FROM f.x OR {TABLE}.y IS DISTINCT FROM f.y
       OR {TABLE}.z IS DISTINCT FROM f.z OR {TABLE}.radius IS DISTINCT FROM f.radius
       OR {TABLE}.is_crafted IS DISTINCT FROM f.is_crafted)"""
upd = count_then_update(con,
    f"SELECT count(*) FROM {TABLE}, fresh f {W}",
    f"""UPDATE {TABLE} SET x = f.x, y = f.y, z = f.z, radius = f.radius,
                          is_crafted = f.is_crafted FROM fresh f {W}""")

sent = con.execute(f"""
INSERT INTO {TABLE} (sector_id, sector, x, y, z, radius, is_crafted)
SELECT 0, '{SENTINEL}', 0, 0, 0, 0, true
WHERE NOT EXISTS (SELECT 1 FROM {TABLE} WHERE sector_id = 0)
RETURNING sector_id""").fetchall()
if sent:
    print(f"  INSERT sentinel sector_id=0 '{SENTINEL}' (for systems with no sector)")

orphan = con.execute(f"""SELECT sector_id, sector FROM {TABLE} t
    WHERE t.sector_id <> 0
      AND NOT EXISTS (SELECT 1 FROM fresh f WHERE f.sector = t.sector)
    ORDER BY sector_id""").fetchall()

after = table_count(con, TABLE)
report_merge(TABLE, before, after, len(ins), upd, orphan)

print("assigning one region per sector...", flush=True)
import numpy as np
from scipy.spatial import cKDTree

lab = con.execute("""
SELECT CAST(e.region AS INTEGER) AS region_id, s.x, s.y, s.z
FROM edastro_star_system e JOIN spansh_system s ON s.name = e.name
WHERE e.region IS NOT NULL AND s.x IS NOT NULL""").df()

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
# region_id carries NO FOREIGN KEY: the column is added after the table exists and
# DuckDB has no ALTER TABLE ADD CONSTRAINT, so this check is the only guard.
print(f"  region_id values not present in `region`: {bad}  "
      f"{'<== BROKEN' if bad else '(clean, though unenforced)'}")

apply_comment_file(con, comment_file(TABLE))

pk = has_primary_key(con, TABLE)
print(f"  {pk or 'NO PRIMARY KEY'}")

ncc = con.execute("""SELECT count(*) FILTER (WHERE comment IS NOT NULL), count(*)
     FROM duckdb_columns() WHERE schema_name = 'main' AND table_name = ?""",
     [TABLE]).fetchone()
print(f"  column comments: {ncc[0]}/{ncc[1]}"
      + ("" if ncc[0] == ncc[1] else "   <== INCOMPLETE, see ETL.md"))

print(f"\n  {'sector kind':<28}{'sectors':>9}{'mean radius':>13}")
for lab, w in (("hand-crafted", "is_crafted"), ("procedural", "NOT is_crafted")):
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

"""Build `system_known` -- all KNOWN (observed, not predicted) systems.

APPROACH (three phases, all intermediates in the `staging` schema):

  1. STAGE every dump into staging.src_system, one row per system, with provenance.
     Sources are added in priority order and each only contributes systems the earlier
     ones do not have:
       spansh   sys_feat            194,696,927   the spine, and the only source with
                                                  declared_body_count
       edsm     edsm_star_system     +2,865,498   REAL systems the spine is missing --
                                                  sys_feat was built from Spansh alone
       edastro  edastro_star_system        +934
     Union universe: 197,561,609 systems, 1.45% of them absent from the spine.

  2. RESOLVE staging.src_system -> staging.sk_ready: parse the name, look up the sector,
     take region from the SECTOR (not per system), attach the primary star and body count.

  3. MERGE into system_known:
       * INSERT systems we do not already have, matched on the natural key
         (sector_id, "system").
       * UPDATE body_count on systems we do have, if it changed. NOTHING ELSE is
         updated -- coordinates, sector, region and primary star are stable facts, and
         re-deriving them on every run would churn 197M rows for nothing.

REGION IS NOW A JOIN, NOT A SPATIAL QUERY. sector.region_id holds one region per sector
(95.0% accurate, see schema/sector_comment.sql), so this costs a 12,064-row hash join
instead of 197,561,609 kNN lookups. Only the 151,446 hand-named systems -- which have no
sector -- still need per-system classification, and that is cheap.

Usage:  python etl/build_system_known.py --limit 200000   # sample, deterministic
        python etl/build_system_known.py --all            # full 197.6M load
        python etl/build_system_known.py --stage-only      # phases 1-2, no merge
        python etl/build_system_known.py --clean-staging   # drop staging tables
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common.db import (ROOT, connect, comment_file, apply_comment_file, report_merge,
                       count_then_update, has_primary_key)

TABLE = "system_known"
PROC = r"^(.*) ([A-Z][A-Z]-[A-Z]) ([a-h])([0-9]+-)?([0-9]+)$"
SENTINEL_SECTOR = 0
BUCKETS = 64          # insert in hash buckets so memory stays bounded on a full load

LOAD_ALL = "--all" in sys.argv
STAGE_ONLY = "--stage-only" in sys.argv
CLEAN = "--clean-staging" in sys.argv
LIMIT = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None

# 197.6M rows: the default 6GB/8-thread profile is for the Spansh parser, not this.
con = connect(memory_limit="20GB", threads=14)
con.execute("CREATE SCHEMA IF NOT EXISTS staging")

if CLEAN:
    for (t,) in con.execute("""SELECT table_name FROM duckdb_tables()
                               WHERE schema_name='staging'""").fetchall():
        n = con.execute(f"SELECT count(*) FROM staging.{t}").fetchone()[0]
        con.execute(f"DROP TABLE staging.{t}")
        print(f"  dropped staging.{t} ({n:,} rows)")
    if not (LIMIT or LOAD_ALL or STAGE_ONLY):
        con.close()
        raise SystemExit("staging cleaned")

# ---------------------------------------------------------------------- DDL ---
WANT = ["system_id", "sector_id", "system", "cube_id", "mass_code", "sub_cube_id",
        "boxel_index", "region_id", "primary_star_body_id", "body_count", "x", "y", "z"]
existed = con.execute("""SELECT count(*) FROM duckdb_tables()
                         WHERE schema_name='main' AND table_name=?""",
                      [TABLE]).fetchone()[0]
if existed:
    have = [r[0] for r in con.execute(f"DESCRIBE {TABLE}").fetchall()]
    if have != WANT:
        n = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
        missing = [c for c in WANT if c not in have]
        if n == 0:
            print(f"  schema differs, table EMPTY -- rebuilding for {missing}")
            con.execute(f"DROP TABLE {TABLE}")
            existed = 0
        else:
            sys.exit(f"{TABLE} has {n:,} rows and is missing {missing}. DuckDB cannot "
                     f"ALTER in a FOREIGN KEY, so this needs a deliberate "
                     f"create-copy-swap migration. Refusing to drop a populated table.")
con.execute(f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    system_id   BIGINT  NOT NULL PRIMARY KEY,
    sector_id   BIGINT  NOT NULL,
    "system"    VARCHAR NOT NULL,
    cube_id     VARCHAR,
    mass_code   VARCHAR,
    sub_cube_id INTEGER,
    boxel_index INTEGER,
    region_id   BIGINT,
    primary_star_body_id INTEGER,
    body_count  INTEGER,
    x           DOUBLE,
    y           DOUBLE,
    z           DOUBLE,
    UNIQUE ("sector_id", "system"),
    FOREIGN KEY (sector_id) REFERENCES sector (sector_id),
    FOREIGN KEY (region_id) REFERENCES region (region_id),
    FOREIGN KEY (primary_star_body_id) REFERENCES body (body_id)
)""")
print(f"{TABLE}: {'exists' if existed else 'CREATED'}, "
      f"{con.execute(f'SELECT count(*) FROM {TABLE}').fetchone()[0]:,} row(s)")
apply_comment_file(con, comment_file(TABLE))

if not (LIMIT or LOAD_ALL or STAGE_ONLY):
    print("\n  no --limit / --all / --stage-only: DDL and comments only, nothing loaded.")
    con.close()
    raise SystemExit

# ------------------------------------------------------ PHASE 1: stage dumps ---
# Filter applied to every source identically so a sample is a coherent slice of the
# universe rather than a slice of one dump.
SAMPLE = "" if (LOAD_ALL or STAGE_ONLY and not LIMIT) else \
    f"AND hash(name) % {max(1, 200_000_000 // max(LIMIT or 1, 1))} = 0"
if LOAD_ALL:
    SAMPLE = ""
print(f"\nPHASE 1  staging dumps ({'ALL' if not SAMPLE else f'~{LIMIT} sample'})...",
      flush=True)

con.execute(f"""
CREATE OR REPLACE TABLE staging.src_system AS
SELECT system_id64, name, x, y, z, declared_body_count, 'spansh' AS source
FROM sys_feat
WHERE x IS NOT NULL AND y IS NOT NULL AND z IS NOT NULL {SAMPLE}
""")
# The SPINE ITSELF holds 1,463 names more than once under different id64s, which would
# break the one-row-per-system grain and then violate UNIQUE (sector_id, "system") on
# merge. DISTINCT ON would sort all 194.7M rows; since only ~1.5k names are affected,
# find those and delete the losers instead. Keep the row carrying declared_body_count
# (the scarcest column), then the lowest id64 for determinism.
con.execute("""
CREATE OR REPLACE TABLE staging.dupe_name AS
SELECT name FROM staging.src_system GROUP BY 1 HAVING count(*) > 1""")
nd = con.execute("SELECT count(*) FROM staging.dupe_name").fetchone()[0]
if nd:
    con.execute("""
    CREATE OR REPLACE TABLE staging.dupe_keep AS
    SELECT name,
           min_by(system_id64, (declared_body_count IS NULL, system_id64)) AS keep_id
    FROM staging.src_system
    WHERE name IN (SELECT name FROM staging.dupe_name)
    GROUP BY 1""")
    con.execute("""
    DELETE FROM staging.src_system
    WHERE name IN (SELECT name FROM staging.dupe_name)
      AND system_id64 NOT IN (SELECT keep_id FROM staging.dupe_keep)""")
n0 = con.execute("SELECT count(*) FROM staging.src_system").fetchone()[0]
print(f"  spansh  (sys_feat)          {n0:>14,}"
      + (f"   ({nd:,} duplicate name(s) collapsed)" if nd else ""))

# EDSM: only systems the spine does not have. Matched on NAME, not id64 -- 54 systems
# exist under two different id64s, and the name is what the sector parse needs.
con.execute(f"""
INSERT INTO staging.src_system
-- DISTINCT ON name: EDSM itself holds 54 systems twice under different id64s, so an
-- unguarded insert would break the one-row-per-system grain. Lowest id64 wins, for
-- determinism.
SELECT DISTINCT ON (e.name)
       e.id64, e.name,
       CAST(e.coords.x AS DOUBLE), CAST(e.coords.y AS DOUBLE), CAST(e.coords.z AS DOUBLE),
       NULL, 'edsm'
FROM edsm_star_system e
WHERE e.coords IS NOT NULL AND e.name IS NOT NULL {SAMPLE.replace('name', 'e.name')}
  AND NOT EXISTS (SELECT 1 FROM staging.src_system s WHERE s.name = e.name)
ORDER BY e.name, e.id64
""")
n1 = con.execute("SELECT count(*) FROM staging.src_system").fetchone()[0]
print(f"  + edsm  (not in the spine)  {n1 - n0:>14,}")

con.execute(f"""
INSERT INTO staging.src_system
SELECT DISTINCT ON (a.name) NULL, a.name, s.x, s.y, s.z, NULL, 'edastro'
FROM edastro_star_system a
LEFT JOIN spansh_system s ON s.name = a.name
WHERE a.name IS NOT NULL {SAMPLE.replace('name', 'a.name')}
  AND NOT EXISTS (SELECT 1 FROM staging.src_system t WHERE t.name = a.name)
  AND s.x IS NOT NULL
ORDER BY a.name
""")
n2 = con.execute("SELECT count(*) FROM staging.src_system").fetchone()[0]
print(f"  + edastro                   {n2 - n1:>14,}")
print(f"  staged universe             {n2:>14,}")

dupe = con.execute("""SELECT count(*) FROM (SELECT name FROM staging.src_system
                      GROUP BY 1 HAVING count(*) > 1)""").fetchone()[0]
if dupe:
    sys.exit(f"staging.src_system has {dupe:,} duplicate names -- refusing to continue")

# --------------------------------------------- PHASE 2: parse and resolve ------
print("\nPHASE 2  resolving...", flush=True)

# The primary star, staged once. This is the expensive scan: 569.7M body rows collapsed
# to one row per system. Restricted to staged systems so a sample stays cheap.
con.execute("""
CREATE OR REPLACE TABLE staging.primary_star AS
SELECT b.system_id64, any_value(b.sub_type) AS sub_type
FROM spansh_body b
WHERE b.main_star AND b.type = 'Star' AND b.sub_type IS NOT NULL
  AND EXISTS (SELECT 1 FROM staging.src_system s WHERE s.system_id64 = b.system_id64)
GROUP BY 1
""")
nps = con.execute("SELECT count(*) FROM staging.primary_star").fetchone()[0]
print(f"  primary stars found        {nps:>14,}")

# Parse, then resolve sector -> region in the SAME join. sector.region_id is why this is
# cheap: no per-system spatial query.
con.execute(f"""
CREATE OR REPLACE TABLE staging.sk_ready AS
WITH p AS (
  SELECT s.system_id64, s.name, s.x, s.y, s.z, s.declared_body_count, s.source,
         regexp_matches(s.name, '{PROC}')                       AS is_proc,
         nullif(regexp_extract(s.name, '{PROC}', 1), '')         AS sector_name,
         CASE WHEN regexp_matches(s.name, '{PROC}')
              THEN regexp_replace(s.name, '{PROC}', '\\2 \\3\\4\\5')
              ELSE s.name END                                    AS "system",
         nullif(regexp_extract(s.name, '{PROC}', 2), '')          AS cube_id,
         nullif(regexp_extract(s.name, '{PROC}', 3), '')          AS mass_code,
         CASE WHEN regexp_matches(s.name, '{PROC}') THEN CAST(coalesce(
              nullif(rtrim(regexp_extract(s.name, '{PROC}', 4), '-'), ''), '0')
              AS INTEGER) END                                    AS sub_cube_id,
         CASE WHEN regexp_matches(s.name, '{PROC}')
              THEN CAST(regexp_extract(s.name, '{PROC}', 5) AS INTEGER) END
                                                                 AS boxel_index
  FROM staging.src_system s
)
SELECT p.system_id64, p.name, p."system",
       coalesce(sc.sector_id, {SENTINEL_SECTOR})  AS sector_id,
       p.cube_id, p.mass_code, p.sub_cube_id, p.boxel_index,
       sc.region_id                               AS region_id,
       bo.body_id                                 AS primary_star_body_id,
       p.declared_body_count                      AS body_count,
       p.x, p.y, p.z, p.source
FROM p
LEFT JOIN sector sc ON sc.sector = p.sector_name
LEFT JOIN staging.primary_star ms ON ms.system_id64 = p.system_id64
LEFT JOIN body bo ON bo.body = ms.sub_type AND bo.type = 'star'
""")
r = con.execute("""SELECT count(*), count(*) FILTER (WHERE sector_id = 0),
       count(region_id), count(primary_star_body_id), count(body_count)
       FROM staging.sk_ready""").fetchone()
print(f"  resolved                   {r[0]:>14,}")
print(f"    hand-named (sector 0)    {r[1]:>14,}")
print(f"    region from sector       {r[2]:>14,}  ({100.0*r[2]/r[0]:.2f}%)")
print(f"    primary star             {r[3]:>14,}  ({100.0*r[3]/r[0]:.2f}%)")
print(f"    body_count               {r[4]:>14,}  ({100.0*r[4]/r[0]:.2f}%)")

# Hand-named systems have no sector, so no region came from the join. There are only
# ~151k of them, so classify those individually -- the one place a spatial query survives.
need = con.execute("""SELECT count(*) FROM staging.sk_ready
                      WHERE region_id IS NULL""").fetchone()[0]
if need:
    import numpy as np
    from scipy.spatial import cKDTree
    lab = con.execute("""
        SELECT CAST(e.region AS INTEGER) AS region_id, s.x, s.y, s.z
        FROM edastro_star_system e JOIN spansh_system s ON s.name = e.name
        WHERE e.region IS NOT NULL AND s.x IS NOT NULL""").df()
    pts = con.execute("""SELECT name, x, y, z FROM staging.sk_ready
                         WHERE region_id IS NULL""").df()
    tree = cKDTree(lab[["x", "y", "z"]].to_numpy())
    _, idx = tree.query(pts[["x", "y", "z"]].to_numpy(), k=5, workers=-1)
    votes = lab["region_id"].to_numpy()[idx]
    pred = np.array([np.bincount(v).argmax() for v in votes], dtype=np.int64)
    con.register("_hn", pts[["name"]].assign(region_id=pred))
    con.execute("CREATE OR REPLACE TABLE staging.hand_named_region AS SELECT * FROM _hn")
    con.execute("""UPDATE staging.sk_ready SET region_id = h.region_id
                   FROM staging.hand_named_region h
                   WHERE staging.sk_ready.name = h.name""")
    print(f"  region by kNN (no sector)  {need:>14,}  <- the only spatial query left")

if STAGE_ONLY:
    print("\n  --stage-only: staging.sk_ready is built, nothing merged.")
    con.close()
    raise SystemExit

# --------------------------------------------------------- PHASE 3: merge ------
print(f"\nPHASE 3  merging in {BUCKETS} bucket(s)...", flush=True)
before = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
inserted = 0
for b in range(BUCKETS):
    con.execute(f"""
    INSERT INTO {TABLE} (system_id, sector_id, "system", cube_id, mass_code,
                         sub_cube_id, boxel_index, region_id, primary_star_body_id,
                         body_count, x, y, z)
    SELECT (SELECT coalesce(max(system_id), 0) FROM {TABLE})
             + row_number() OVER (ORDER BY t.sector_id, t."system"),
           t.sector_id, t."system", t.cube_id, t.mass_code, t.sub_cube_id,
           t.boxel_index, t.region_id, t.primary_star_body_id, t.body_count,
           t.x, t.y, t.z
    FROM staging.sk_ready t
    WHERE hash(t.name) % {BUCKETS} = {b}
      AND NOT EXISTS (SELECT 1 FROM {TABLE} k
                      WHERE k.sector_id = t.sector_id AND k."system" = t."system")
    """)
    now = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
    if BUCKETS > 1 and (b + 1) % 8 == 0:
        print(f"    bucket {b+1:>3}/{BUCKETS}   {now:,} rows", flush=True)
    inserted = now - before

# Only body_count is refreshed for systems we already hold: it is the one value that
# genuinely changes as people honk. Coordinates, sector, region and primary star are
# stable, and re-deriving them every run would churn 197M rows to no purpose.
# No RETURNING -- DuckDB blocks it on FK-referenced rows (see common.db).
_W = f"""WHERE {TABLE}.sector_id = t.sector_id AND {TABLE}."system" = t."system"
  AND t.body_count IS NOT NULL
  AND {TABLE}.body_count IS DISTINCT FROM t.body_count"""
upd = count_then_update(con,
    f"SELECT count(*) FROM {TABLE}, staging.sk_ready t {_W}",
    f"UPDATE {TABLE} SET body_count = t.body_count FROM staging.sk_ready t {_W}")

after = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
report_merge(TABLE, before, after, inserted, upd, [])

print(f"  {has_primary_key(con, TABLE)}")
print(f"\n  {'source of the staged universe':<34}{'n':>14}")
for s_, n in con.execute("""SELECT source, count(*) FROM staging.sk_ready
                            GROUP BY 1 ORDER BY 2 DESC""").fetchall():
    print(f"  {s_:<34}{n:>14,}")

print(f"\n  {'column coverage in ' + TABLE:<34}{'n':>14}{'%':>8}")
tot = max(after, 1)
for lab_, w in (("sector_id <> 0 (real sector)", "sector_id <> 0"),
                ("region_id", "region_id IS NOT NULL"),
                ("mass_code", "mass_code IS NOT NULL"),
                ("primary_star_body_id", "primary_star_body_id IS NOT NULL"),
                ("body_count", "body_count IS NOT NULL")):
    c = con.execute(f"SELECT count(*) FROM {TABLE} WHERE {w}").fetchone()[0]
    print(f"  {lab_:<34}{c:>14,}{100.0*c/tot:>7.2f}%")

print(f"\n  staging (PERSISTS -- --clean-staging to drop):")
for t, n in con.execute("""SELECT table_name, estimated_size FROM duckdb_tables()
                           WHERE schema_name='staging' ORDER BY estimated_size DESC
                           LIMIT 8""").fetchall():
    print(f"    staging.{t:<24}{(n or 0):>14,} rows")
con.close()
print("\nDONE_BUILD_SYSTEM_KNOWN")

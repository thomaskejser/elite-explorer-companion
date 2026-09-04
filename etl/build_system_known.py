"""Build `system_known` -- all KNOWN (observed, not predicted) systems.

APPROACH (three phases, all intermediates in the `staging` schema):

  1. STAGE every dump into staging.src_system, one row per system, with provenance.
     Sources are added in priority order and each only contributes systems the earlier
     ones do not have:
       spansh   staging.spansh_system 194,696,927 the spine, and the only source with
                                                  declared_body_count
       edsm     edsm_star_system     +2,865,498   REAL systems the spine is missing --
                                                  the raw Spansh galaxy dump
       edastro  edastro_star_system        +934
     Union universe: 197,561,609 systems, 1.45% of them absent from the spine.

  2. RESOLVE staging.src_system -> staging.sk_ready: parse the name, look up the sector,
     take region from the SECTOR (not per system), attach the primary star and body count.

  3. MERGE into system_known:
       * INSERT systems we do not already have, matched on the natural key
         (sector_id, system_in_sector).
       * UPDATE body_count on systems we do have, if it changed. NOTHING ELSE is
         updated -- coordinates, sector, region and primary star are stable facts, and
         re-deriving them on every run would churn 197M rows for nothing.

REGION IS NOW A JOIN, NOT A SPATIAL QUERY. sector.region_id holds one region per sector
(95.0% accurate, see schema/sector.sql), so this costs a 12,064-row hash join
instead of 197,561,609 kNN lookups. Only the 151,446 hand-named systems -- which have no
sector -- still need per-system classification, and that is cheap.

Usage:  python etl/build_system_known.py --limit 200000   # sample, deterministic
        python etl/build_system_known.py --all            # full 197.6M load
        python etl/build_system_known.py --stage-only      # phases 1-2, no merge
        python etl/build_system_known.py --clean-staging   # drop staging tables
        python etl/build_system_known.py --id64            # backfill id64 only
        python etl/build_system_known.py --poi             # link system-level POIs
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common.db import (ROOT, connect, comment_file, apply_comment_file, report_merge,
                       count_then_update, has_primary_key)

TABLE = "system_known"
PROC = r"^(.*) ([A-Z][A-Z]-[A-Z]) ([a-h])([0-9]+-)?([0-9]+)$"
SENTINEL_SECTOR = 0
# *** BUCKETS ARE FOR A FULL LOAD AND ARE PURE OVERHEAD ON A DELTA. ***
# Every bucket anti-joins the WHOLE 197.7M-row table on (sector_id, system_in_sector),
# which carries no index -- so its cost is one hash join per bucket no matter how few
# rows that bucket inserts. Splitting a 197M-row first load 64 ways keeps peak memory
# bounded and earns its keep. Splitting a 3.8M-row monthly delta 64 ways pays that join
# 64 times over to insert ~60k rows each, and measured, that is hours against minutes.
#
# So the count follows the SIZE OF THE STAGED SET; --buckets N overrides it.
BUCKETS_FULL, BUCKETS_DELTA, DELTA_MAX = 64, 4, 20_000_000

LOAD_ALL = "--all" in sys.argv
BUCKET_ARG = (int(sys.argv[sys.argv.index("--buckets") + 1])
              if "--buckets" in sys.argv else None)
STAGE_ONLY = "--stage-only" in sys.argv
CLEAN = "--clean-staging" in sys.argv
POI = "--poi" in sys.argv
ID64 = "--id64" in sys.argv
LIMIT = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None

# 197.6M rows: the default 6GB/8-thread profile is for the Spansh parser, not this.
con = connect(memory_limit="20GB", threads=14)
con.execute("CREATE SCHEMA IF NOT EXISTS staging")

if CLEAN:
    # TRUNCATE, NEVER DROP. The database's shape -- model and staging alike -- is
    # created once when the database is made and does not change afterwards, so this
    # empties tables and leaves their structure, constraints and comments intact.
    # Dropping would silently redefine the schema on the next run.
    #
    # RAW SOURCE tables are skipped: they are downloaded input, not work tables, and
    # emptying staging.spansh_body means re-downloading and re-parsing a multi-hour
    # dump. Pass --include-raw to empty those too, knowingly.
    raw = {r[0] for r in con.execute(
        """SELECT table_name FROM duckdb_tables()
           WHERE schema_name='staging' AND comment LIKE 'RAW SOURCE%'""").fetchall()}
    for (t,) in con.execute("""SELECT table_name FROM duckdb_tables()
                               WHERE schema_name='staging'
                               ORDER BY table_name""").fetchall():
        n = con.execute(f"SELECT count(*) FROM staging.{t}").fetchone()[0]
        if t in raw and "--include-raw" not in sys.argv:
            print(f"  KEPT staging.{t} ({n:,} rows) -- RAW SOURCE, downloaded input")
            continue
        con.execute(f"TRUNCATE staging.{t}")
        print(f"  truncated staging.{t} ({n:,} rows removed, table kept)")
    if not (LIMIT or LOAD_ALL or STAGE_ONLY):
        con.close()
        raise SystemExit("staging cleaned")

# ---------------------------------------------------------------------- DDL ---
WANT = ["system_id", "sector_id", "system_in_sector", "cube_id", "mass_code", "sub_cube_id",
        "boxel_index", "region_id", "primary_star_body_id", "body_count", "x", "y", "z"]
# Columns added AFTER the table existed. They are checked for presence, never for
# position, and they carry NO enforced foreign key on an existing database -- DuckDB
# has no ALTER TABLE ADD CONSTRAINT, so the FK in the CREATE below binds only on a
# fresh build. Keeping them out of WANT is what stops the drift guard below from
# demanding a create-copy-swap of a 197.6M-row table every time one is added.
ADDITIVE = {"id_poi": "INTEGER", "id64": "BIGINT"}
existed = con.execute("""SELECT count(*) FROM duckdb_tables()
                         WHERE schema_name='main' AND table_name=?""",
                      [TABLE]).fetchone()[0]
if existed:
    have = [r[0] for r in con.execute(f"DESCRIBE {TABLE}").fetchall()]
    # Compare only the CORE columns, and only for presence: an ADDITIVE column that
    if [c for c in have if c not in ADDITIVE] != WANT:
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
# DDL COMES FROM schema/{TABLE}.sql, NOT FROM A COPY HERE. That file is the single
# source of truth for the table shape AND its comments, and it is what a fresh build of
# the database must read (ETL.md, "Schema changes"). An inline copy
# drifted from it once already: this builder still declared a
# UNIQUE(system_id, system_body) and three FOREIGN KEYs that measurement showed
# cannot be populated at 570.8M rows, so a fresh build from here produced a
# table that could never be loaded.
# (system_known is under the size wall and keeps all of its constraints.)
con.execute(comment_file(TABLE).read_text(encoding="utf-8"))
print(f"{TABLE}: {'exists' if existed else 'CREATED'}, "
      f"{con.execute(f'SELECT count(*) FROM {TABLE}').fetchone()[0]:,} row(s)")
# ADDITIVE columns are migrated in BEFORE the comments are applied: a COMMENT ON
# COLUMN for a column that does not exist yet is a hard BinderException, so this order
# is load-bearing, not cosmetic.
#
# *** The FOREIGN KEY on id_poi in the CREATE above binds only on a FRESH database.
# DuckDB has no ALTER TABLE ADD CONSTRAINT, so here it is an unenforced integer and
# nothing stops a dangling poi_id. The --poi phase validates it in SQL after writing,
# which is the only guard this database gets. ***

apply_comment_file(con, comment_file(TABLE))

if ID64:
    # --------------------------------------------------- PHASE I: backfill id64 ---
    # Phase 3 carries system_id64 through on INSERT; this fills the column on rows
    # that arrived without it, from staging.sys_bridge, which IS that mapping.
    #
    # Once every row has an id64, sys_bridge stops being load-bearing: common/poi_link.py
    # and build_system_phenomenon.py can join system_known directly rather than through
    # a 197.5M-row staging table.
    if not con.execute("""SELECT count(*) FROM duckdb_tables()
            WHERE schema_name='staging' AND table_name='sys_bridge'""").fetchone()[0]:
        sys.exit("staging.sys_bridge is missing -- it is the id64 -> system_id mapping.\n"
                 "Run: python etl/build_system_known.py --all")
    print("\nPHASE I  backfilling id64 from staging.sys_bridge...", flush=True)

    _W = """WHERE system_known.system_id = g.system_id
              AND system_known.id64 IS DISTINCT FROM g.system_id64"""
    upd = count_then_update(con,
        f"SELECT count(*) FROM system_known, staging.sys_bridge g {_W}",
        f"UPDATE system_known SET id64 = g.system_id64 FROM staging.sys_bridge g {_W}")

    tot, have = con.execute("""SELECT count(*), count(id64) FROM system_known""").fetchone()
    print(f"    {upd:,} row(s) updated")
    print(f"    id64 known on {have:,} / {tot:,} ({100.0*have/max(tot,1):.4f}%), "
          f"{tot - have:,} still NULL")

    # id64 is unique in the GAME. Where two of OUR rows share one, we have recorded the
    # same system twice under different name spellings -- a defect, not id64 reuse.
    dup = con.execute("""SELECT count(*) FROM (SELECT id64 FROM system_known
        WHERE id64 IS NOT NULL GROUP BY 1 HAVING count(*) > 1)""").fetchone()[0]
    print(f"    id64 values on >1 row: {dup:,}"
          f"{'  <== duplicate SYSTEMS, see the column comment' if dup else '  (ok)'}")
    if dup:
        print(con.execute("""SELECT k.id64, string_agg(k.system_in_sector, ' | ') AS spellings
            FROM system_known k WHERE k.id64 IN (SELECT id64 FROM system_known
                WHERE id64 IS NOT NULL GROUP BY 1 HAVING count(*) > 1)
            GROUP BY 1 ORDER BY 1 LIMIT 10""").fetchdf().to_string(index=False))
    apply_comment_file(con, comment_file(TABLE))
    con.close()
    raise SystemExit("\nDONE_BACKFILL_ID64")

if POI:
    # --------------------------------------------------- PHASE P: link POIs ---
    # SYSTEM-LEVEL POIs only. Anything Canonn pins to a named body belongs to
    # system_body.id_poi instead, and build_system_body.py --poi writes those; the
    # split is decided once in common/poi_link.py so the two cannot disagree.
    from common.poi_link import stage_poi_events, winner_sql
    print("\nPHASE P  linking system-level POIs...", flush=True)
    stage_poi_events(con)

    con.execute(f"""CREATE OR REPLACE TABLE staging.poi_sys AS
        {winner_sql(['system_id'], 'body_suffix IS NULL')}""")
    n = con.execute("SELECT count(*) FROM staging.poi_sys").fetchone()[0]
    print(f"    {n:,} systems get a system-level id_poi (rarest POI wins)")

    _W = """WHERE system_known.system_id = w.system_id
              AND system_known.id_poi IS DISTINCT FROM w.poi_id"""
    upd = count_then_update(con,
        f"SELECT count(*) FROM system_known, staging.poi_sys w {_W}",
        f"UPDATE system_known SET id_poi = w.poi_id FROM staging.poi_sys w {_W}")
    print(f"    {upd:,} row(s) updated")

    # Rows whose POI moved to a body, or whose source row vanished, must be CLEARED --
    # otherwise a stale id_poi outlives the observation that justified it. This is not
    # a delete: the system row stays, only the attribute is reset.
    _WC = """WHERE system_known.id_poi IS NOT NULL
               AND NOT EXISTS (SELECT 1 FROM staging.poi_sys w
                               WHERE w.system_id = system_known.system_id)"""
    cl = count_then_update(con,
        f"SELECT count(*) FROM system_known {_WC}",
        f"UPDATE system_known SET id_poi = NULL {_WC}")
    print(f"    {cl:,} stale id_poi cleared")

    bad = con.execute("""SELECT count(*) FROM system_known k WHERE k.id_poi IS NOT NULL
        AND NOT EXISTS (SELECT 1 FROM poi p WHERE p.poi_id = k.id_poi)""").fetchone()[0]
    print(f"    dangling id_poi (FK is UNENFORCED on this database): {bad:,}"
          f"{'  <== BROKEN' if bad else '  (ok)'}")
    print(con.execute("""SELECT p.poi_class, count(*) systems FROM system_known k
        JOIN poi p ON p.poi_id = k.id_poi GROUP BY 1 ORDER BY 2 DESC""")
        .fetchdf().to_string(index=False))
    apply_comment_file(con, comment_file(TABLE))
    con.close()
    raise SystemExit("\nDONE_LINK_POI")

if not (LIMIT or LOAD_ALL or STAGE_ONLY):
    print("\n  no --limit / --all / --stage-only / --poi / --id64: DDL and comments only, "
          "nothing loaded.")
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
-- Straight from staging.spansh_system: name, coordinates and declared_body_count as
-- the dump reports them, with nothing derived. Everything derived -- mass_code,
-- r_sgra/plane_r/height, is_scanned, has_bh/has_wr/has_neutron -- is computed from
-- system_known and system_body JOIN body, never carried along here.
SELECT system_id64, name, x, y, z, declared_body_count, 'spansh' AS source
FROM staging.spansh_system
WHERE x IS NOT NULL AND y IS NOT NULL AND z IS NOT NULL {SAMPLE}
""")
# The SPINE ITSELF holds 1,463 names more than once under different id64s, which would
# break the one-row-per-system grain and then violate UNIQUE (sector_id, system_in_sector) on
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
print(f"  spansh  (staging)           {n0:>14,}"
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
       -- *** THE SENTINEL IS ONLY EVER CORRECT FOR A NAME THAT STANDS ALONE. ***
       -- A procedural name whose sector is missing from `sector` must NOT fall
       -- through to coalesce(..., 0): that throws the sector prefix away and files
       -- "Pria Scrio AA-H d10-0" as a HAND-NAMED system called "AA-H d10-0". Two such
       -- systems in different unknown sectors then collide on (0, name) and the merge
       -- dies on the primary key.
       --
       -- NULL here means "procedural, sector unknown"; those rows are filtered out
       -- below and reported, because the fix is to run etl/build_sector.py first, not
       -- to invent a sector. New sectors DO appear -- this delta brought 27.
       CASE WHEN sc.sector_id IS NOT NULL THEN sc.sector_id
            WHEN NOT regexp_matches(p.name, '{PROC}') THEN {SENTINEL_SECTOR}
       END                                        AS sector_id,
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
orphan_sector = con.execute(
    "SELECT count(*) FROM staging.sk_ready WHERE sector_id IS NULL").fetchone()[0]
if orphan_sector:
    pat = "^(.*) [A-Z][A-Z]-[A-Z] [a-h][0-9]"
    names = [r[0] for r in con.execute(
        "SELECT DISTINCT regexp_extract(name, ?, 1) FROM staging.sk_ready "
        "WHERE sector_id IS NULL LIMIT 8", [pat]).fetchall()]
    con.execute("DELETE FROM staging.sk_ready WHERE sector_id IS NULL")
    print(f"  *** {orphan_sector:,} procedural system(s) EXCLUDED -- their sector is "
          f"not in `sector` yet.\n"
          f"      Run etl/build_sector.py, then re-run this; until then they stay "
          f"missing.\n"
          f"      sectors: {', '.join(names)}", flush=True)

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
staged_rows = con.execute("SELECT count(*) FROM staging.sk_ready").fetchone()[0]
BUCKETS = BUCKET_ARG or (BUCKETS_DELTA if staged_rows <= DELTA_MAX
                         else BUCKETS_FULL)
print(f"\nPHASE 3  merging {staged_rows:,} staged row(s) in {BUCKETS} bucket(s)...", flush=True)
before = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
inserted = 0
for b in range(BUCKETS):
    con.execute(f"""
    INSERT INTO {TABLE} (system_id, sector_id, system_in_sector, cube_id, mass_code,
                         sub_cube_id, boxel_index, region_id, primary_star_body_id,
                         body_count, x, y, z, id64)
    SELECT (SELECT coalesce(max(system_id), 0) FROM {TABLE})
             + row_number() OVER (ORDER BY t.sector_id, t."system"),
           t.sector_id, t."system", t.cube_id, t.mass_code, t.sub_cube_id,
           t.boxel_index, t.region_id, t.primary_star_body_id, t.body_count,
           t.x, t.y, t.z, t.system_id64
    FROM staging.sk_ready t
    WHERE hash(t.name) % {BUCKETS} = {b}
      AND NOT EXISTS (SELECT 1 FROM {TABLE} k
                      WHERE k.sector_id = t.sector_id AND k.system_in_sector = t."system")
    """)
    now = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
    if BUCKETS > 1 and (b + 1) % max(1, BUCKETS // 8) == 0:
        print(f"    bucket {b+1:>3}/{BUCKETS}   {now:,} rows", flush=True)
    inserted = now - before

# Only body_count is refreshed for systems we already hold: it is the one value that
# genuinely changes as people honk. Coordinates, sector, region and primary star are
# stable, and re-deriving them every run would churn 197M rows to no purpose.
# No RETURNING -- DuckDB blocks it on FK-referenced rows (see common.db).
_W = f"""WHERE {TABLE}.sector_id = t.sector_id AND {TABLE}.system_in_sector = t."system"
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

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (apply_comment_file, comment_file, connect, count_then_update,
                       has_primary_key, prepare_table, report_merge, table_count)

TABLE = "system_known"
PROC = r"^(.*) ([A-Z][A-Z]-[A-Z]) ([a-h])([0-9]+-)?([0-9]+)$"
SENTINEL_SECTOR = 0
BUCKETS_FULL, BUCKETS_DELTA, DELTA_MAX = 64, 4, 20_000_000

LOAD_ALL = "--all" in sys.argv
BUCKET_ARG = (int(sys.argv[sys.argv.index("--buckets") + 1])
              if "--buckets" in sys.argv else None)
STAGE_ONLY = "--stage-only" in sys.argv
CLEAN = "--clean-staging" in sys.argv
POI = "--poi" in sys.argv
ID64 = "--id64" in sys.argv
LIMIT = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None

con = connect(memory_limit="20GB", threads=14)
con.execute("CREATE SCHEMA IF NOT EXISTS staging")

# TRUNCATEs staging, which ETL.md 3b permits only for work tables -- so tables
# commented RAW SOURCE are skipped unless --include-raw says otherwise.
if CLEAN:
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

WANT = ["system_id", "sector_id", "system_in_sector", "cube_id", "mass_code", "sub_cube_id",
        "boxel_index", "region_id", "primary_star_body_id", "body_count", "x", "y", "z"]
# ADDITIVE columns are added after creation, so the FOREIGN KEY on id_poi cannot
# bind (DuckDB has no ALTER TABLE ADD CONSTRAINT). --poi validates it in SQL.
ADDITIVE = {"id_poi": "INTEGER", "id64": "BIGINT"}
existed = con.execute("""SELECT count(*) FROM duckdb_tables()
                         WHERE schema_name='main' AND table_name=?""",
                      [TABLE]).fetchone()[0]
if existed:
    have = [r[0] for r in con.execute(f"DESCRIBE {TABLE}").fetchall()]
    if [c for c in have if c not in ADDITIVE] != WANT:
        n = table_count(con, TABLE)
        missing = [c for c in WANT if c not in have]
        if n == 0:
            print(f"  schema differs, table EMPTY -- rebuilding for {missing}")
            # DROP, which merge-never-drop forbids: reachable only when the table is
            # EMPTY and its shape is wrong. A populated one exits instead.
            con.execute(f"DROP TABLE {TABLE}")
            existed = 0
        else:
            sys.exit(f"{TABLE} has {n:,} rows and is missing {missing}. DuckDB cannot "
                     f"ALTER in a FOREIGN KEY, so this needs a deliberate "
                     f"create-copy-swap migration. Refusing to drop a populated table.")
prepare_table(con, TABLE, "staging.src_known")
print(f"  table {'existed' if existed else 'was CREATED by this run'}")

if ID64:
    if not con.execute("""SELECT count(*) FROM duckdb_tables()
            WHERE schema_name='staging' AND table_name='sys_bridge'""").fetchone()[0]:
        sys.exit("staging.sys_bridge is missing -- it is the id64 -> system_id mapping.\n"
                 "Run: python etl/system_known/build.py --all")
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
    from common.poi_link import stage_poi_events, winner_sql
    print("\nPHASE P  linking system-level POIs...", flush=True)
    stage_poi_events(con)

    con.execute(f"""CREATE OR REPLACE TABLE staging.poi_sys AS
        {winner_sql(['system_id'], 'body_suffix IS NULL')}""")
    n = table_count(con, 'staging.poi_sys')
    print(f"    {n:,} systems get a system-level id_poi (rarest POI wins)")

    _W = """WHERE system_known.system_id = w.system_id
              AND system_known.id_poi IS DISTINCT FROM w.poi_id"""
    upd = count_then_update(con,
        f"SELECT count(*) FROM system_known, staging.poi_sys w {_W}",
        f"UPDATE system_known SET id_poi = w.poi_id FROM staging.poi_sys w {_W}")
    print(f"    {upd:,} row(s) updated")

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

SAMPLE = "" if (LOAD_ALL or STAGE_ONLY and not LIMIT) else \
    f"AND hash(name) % {max(1, 200_000_000 // max(LIMIT or 1, 1))} = 0"
if LOAD_ALL:
    SAMPLE = ""
print(f"\nPHASE 1  staging dumps ({'ALL' if not SAMPLE else f'~{LIMIT} sample'})...",
      flush=True)

con.execute(f"""
CREATE OR REPLACE TABLE staging.src_system AS
SELECT system_id64, name, x, y, z, declared_body_count, 'spansh' AS source
FROM staging.spansh_system
WHERE x IS NOT NULL AND y IS NOT NULL AND z IS NOT NULL {SAMPLE}
""")
con.execute("""
CREATE OR REPLACE TABLE staging.dupe_name AS
SELECT name FROM staging.src_system GROUP BY 1 HAVING count(*) > 1""")
nd = table_count(con, 'staging.dupe_name')
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
n0 = table_count(con, 'staging.src_system')
print(f"  spansh  (staging)           {n0:>14,}"
      + (f"   ({nd:,} duplicate name(s) collapsed)" if nd else ""))

con.execute(f"""
INSERT INTO staging.src_system
SELECT DISTINCT ON (e.name)
       e.id64, e.name,
       CAST(e.coords.x AS DOUBLE), CAST(e.coords.y AS DOUBLE), CAST(e.coords.z AS DOUBLE),
       NULL, 'edsm'
FROM edsm_star_system e
WHERE e.coords IS NOT NULL AND e.name IS NOT NULL {SAMPLE.replace('name', 'e.name')}
  AND NOT EXISTS (SELECT 1 FROM staging.src_system s WHERE s.name = e.name)
ORDER BY e.name, e.id64
""")
n1 = table_count(con, 'staging.src_system')
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
n2 = table_count(con, 'staging.src_system')
print(f"  + edastro                   {n2 - n1:>14,}")
print(f"  staged universe             {n2:>14,}")

dupe = con.execute("""SELECT count(*) FROM (SELECT name FROM staging.src_system
                      GROUP BY 1 HAVING count(*) > 1)""").fetchone()[0]
if dupe:
    sys.exit(f"staging.src_system has {dupe:,} duplicate names -- refusing to continue")

print("\nPHASE 2  resolving...", flush=True)

con.execute("""
CREATE OR REPLACE TABLE staging.primary_star AS
SELECT b.system_id64, any_value(b.sub_type) AS sub_type
FROM spansh_body b
WHERE b.main_star AND b.type = 'Star' AND b.sub_type IS NOT NULL
  AND EXISTS (SELECT 1 FROM staging.src_system s WHERE s.system_id64 = b.system_id64)
GROUP BY 1
""")
nps = table_count(con, 'staging.primary_star')
print(f"  primary stars found        {nps:>14,}")

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
          f"      Run etl/sector/build.py, then re-run this; until then they stay "
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

staged_rows = table_count(con, 'staging.sk_ready')
BUCKETS = BUCKET_ARG or (BUCKETS_DELTA if staged_rows <= DELTA_MAX
                         else BUCKETS_FULL)
print(f"\nPHASE 3  merging {staged_rows:,} staged row(s) in {BUCKETS} bucket(s)...", flush=True)
before = table_count(con, TABLE)
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
    now = table_count(con, TABLE)
    if BUCKETS > 1 and (b + 1) % max(1, BUCKETS // 8) == 0:
        print(f"    bucket {b+1:>3}/{BUCKETS}   {now:,} rows", flush=True)
    inserted = now - before

_W = f"""WHERE {TABLE}.sector_id = t.sector_id AND {TABLE}.system_in_sector = t."system"
  AND t.body_count IS NOT NULL
  AND {TABLE}.body_count IS DISTINCT FROM t.body_count"""
upd = count_then_update(con,
    f"SELECT count(*) FROM {TABLE}, staging.sk_ready t {_W}",
    f"UPDATE {TABLE} SET body_count = t.body_count FROM staging.sk_ready t {_W}")

after = table_count(con, TABLE)
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

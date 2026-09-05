import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (apply_comment_file, comment_file, connect, count_then_update,
                       has_primary_key, prepare_table, report_merge, table_count)

TABLE = "system_body"
BUCKETS_FULL, BUCKETS_DELTA, DELTA_MAX = 128, 8, 60_000_000
BUCKET_ARG = (int(sys.argv[sys.argv.index("--buckets") + 1])
              if "--buckets" in sys.argv else None)

LOAD_ALL = "--all" in sys.argv
STAGE_ONLY = "--stage-only" in sys.argv
CLEAN = "--clean-staging" in sys.argv
POI = "--poi" in sys.argv
DELTA = "--delta" in sys.argv
SRC_SPANSH = "spansh_body_latest" if DELTA else "spansh_body"
SRC_EDSM = "edsm_celestial_body_latest" if DELTA else "edsm_celestial_body"
SRC_EDASTRO = "edastro_planet_latest" if DELTA else "edastro_planet"
REUSE = "--rebuild-staging" not in sys.argv
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

CORE = ["system_body_id", "system_id", "body_id", "system_body", "is_primary",
        "discovered_time"]
# EXTRA columns are added after creation, so the FOREIGN KEY on id_poi cannot
# bind (DuckDB has no ALTER TABLE ADD CONSTRAINT). --poi validates it in SQL.
EXTRA = {"solar_masses": "DOUBLE", "earth_masses": "DOUBLE",
         "is_terraformable": "BOOLEAN", "source": "VARCHAR", "id_poi": "INTEGER"}
existed = con.execute("""SELECT count(*) FROM duckdb_tables()
                         WHERE schema_name='main' AND table_name=?""",
                      [TABLE]).fetchone()[0]
if existed:
    have = [r[0] for r in con.execute(f"DESCRIBE {TABLE}").fetchall()]
    missing_core = [c for c in CORE if c not in have]
    if missing_core:
        n = table_count(con, TABLE)
        if n == 0:
            print(f"  schema differs, table EMPTY -- rebuilding for {missing_core}",
                  flush=True)
            # DROP, which merge-never-drop forbids: reachable only when the table is
            # EMPTY and its shape is wrong. A populated one exits instead.
            con.execute(f"DROP TABLE {TABLE}")
            existed = 0
        else:
            sys.exit(f"{TABLE} has {n:,} rows and is missing {missing_core}. DuckDB "
                     f"cannot ALTER in a FOREIGN KEY -- needs a create-copy-swap "
                     f"migration.")
prepare_table(con, TABLE, "staging.src_body")
print(f"  table {'existed' if existed else 'was CREATED by this run'}")

if POI:
    from common.poi_link import stage_poi_events, winner_sql
    print("\nPHASE P  linking body-level POIs...", flush=True)
    stage_poi_events(con)

    con.execute(f"""CREATE OR REPLACE TABLE staging.poi_body AS
        {winner_sql(['system_id', 'body_suffix'], 'body_suffix IS NOT NULL')}""")
    n = table_count(con, 'staging.poi_body')
    new = con.execute("""SELECT count(*) FROM staging.poi_body w
        WHERE NOT EXISTS (SELECT 1 FROM system_body b
            WHERE b.system_id = w.system_id AND b.system_body = w.body_suffix)""").fetchone()[0]
    virgin = con.execute("""SELECT count(DISTINCT w.system_id) FROM staging.poi_body w
        WHERE NOT EXISTS (SELECT 1 FROM system_body b
                          WHERE b.system_id = w.system_id)""").fetchone()[0]
    print(f"    {n:,} (system, body) POIs -- {new:,} bodies not yet in {TABLE}")
    print(f"    {virgin:,} of those systems have NO body row today and will LEAVE "
          f"system_predicted")

    before = table_count(con, TABLE)
    con.execute(f"""
    INSERT INTO {TABLE} (system_body_id, system_id, body_id, system_body, is_primary,
                         discovered_time, solar_masses, earth_masses, is_terraformable,
                         source, id_poi)
    SELECT coalesce((SELECT max(system_body_id) FROM {TABLE}), 0)
             + row_number() OVER (ORDER BY w.system_id, w.body_suffix),
           w.system_id, NULL, w.body_suffix,
           false, NULL, NULL, NULL, NULL, 'canonn_codex', w.poi_id
    FROM staging.poi_body w
    WHERE NOT EXISTS (SELECT 1 FROM {TABLE} b
                      WHERE b.system_id = w.system_id AND b.system_body = w.body_suffix)
    """)
    mid = table_count(con, TABLE)

    _W = f"""WHERE {TABLE}.system_id = w.system_id
               AND {TABLE}.system_body = w.body_suffix
               AND {TABLE}.id_poi IS DISTINCT FROM w.poi_id"""
    upd = count_then_update(con,
        f"SELECT count(*) FROM {TABLE}, staging.poi_body w {_W}",
        f"UPDATE {TABLE} SET id_poi = w.poi_id FROM staging.poi_body w {_W}")

    _WC = f"""WHERE {TABLE}.id_poi IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM staging.poi_body w
                WHERE w.system_id = {TABLE}.system_id
                  AND w.body_suffix = {TABLE}.system_body)"""
    cl = count_then_update(con,
        f"SELECT count(*) FROM {TABLE} {_WC}",
        f"UPDATE {TABLE} SET id_poi = NULL {_WC}")

    after = table_count(con, TABLE)
    print(f"    {mid - before:,} bodies inserted, {upd:,} id_poi set, "
          f"{cl:,} stale cleared, {before:,} -> {after:,} rows")

    bad = con.execute(f"""SELECT count(*) FROM {TABLE} b WHERE b.id_poi IS NOT NULL
        AND NOT EXISTS (SELECT 1 FROM poi p WHERE p.poi_id = b.id_poi)""").fetchone()[0]
    dup = con.execute(f"""SELECT count(*) FROM (SELECT system_id FROM {TABLE}
        WHERE is_primary GROUP BY 1 HAVING count(*) > 1)""").fetchone()[0]
    print(f"    dangling id_poi (FK is UNENFORCED on this database): {bad:,}"
          f"{'  <== BROKEN' if bad else '  (ok)'}")
    print(f"    systems with >1 is_primary row: {dup:,}"
          f"{'  <== BROKEN' if dup else '  (ok)'}")
    print(con.execute(f"""SELECT p.poi_class, count(*) bodies FROM {TABLE} b
        JOIN poi p ON p.poi_id = b.id_poi GROUP BY 1 ORDER BY 2 DESC""")
        .fetchdf().to_string(index=False))
    apply_comment_file(con, comment_file(TABLE))
    con.close()
    raise SystemExit("\nDONE_LINK_POI")

if not (LIMIT or LOAD_ALL or STAGE_ONLY):
    print("\n  no --limit / --all / --stage-only / --poi: DDL and comments only.",
          flush=True)
    con.close()
    raise SystemExit

have_ready = con.execute("""SELECT count(*) FROM duckdb_tables()
    WHERE schema_name='staging' AND table_name='sk_ready'""").fetchone()[0]
if not have_ready:
    sys.exit("staging.sk_ready is missing -- it is the id64 -> system_id bridge.\n"
             "Run: python etl/system_known/build.py --all")
have_bridge = con.execute("""SELECT count(*) FROM duckdb_tables()
    WHERE schema_name='staging' AND table_name='sys_bridge'""").fetchone()[0]
have_src0 = con.execute("""SELECT count(*) FROM duckdb_tables()
    WHERE schema_name='staging' AND table_name='src_body'""").fetchone()[0]
if have_bridge and have_src0 and REUSE:
    nb = table_count(con, 'staging.sys_bridge')
    print(f"\nbridge reused ({nb:,} rows) -- only Phase 1 needs it", flush=True)
else:
  print("\nbuilding the id64 -> system_id bridge...", flush=True)
  con.execute(f"""
CREATE OR REPLACE TABLE staging.sys_bridge AS
SELECT k.id64 AS system_id64, k.system_id,
       CASE WHEN sc.sector IS NULL OR k.sector_id = 0 THEN k.system_in_sector
            ELSE sc.sector || ' ' || k.system_in_sector END AS sys_name
FROM system_known k LEFT JOIN sector sc ON sc.sector_id = k.sector_id
WHERE k.id64 IS NOT NULL
""")
  nb = table_count(con, 'staging.sys_bridge')
  nk = table_count(con, 'system_known')
  print(f"  bridged {nb:,} of {nk:,} system_known rows "
        f"({100.0*nb/max(nk,1):.2f}%; the rest have no id64 -- EDAstro-sourced)",
        flush=True)

SAMPLE = "" if LOAD_ALL else \
    f"AND hash(b.name) % {max(1, 600_000_000 // max(LIMIT or 1, 1))} = 0"

SRC_COLS = ["system_id", "sys_name", "body_name", "body_type", "sub_type", "is_primary",
            "source", "solar_masses", "earth_masses", "is_terraformable"]
have_src = con.execute("""SELECT count(*) FROM duckdb_tables()
    WHERE schema_name='staging' AND table_name='src_body'""").fetchone()[0]
src_stale = []
if have_src:
    _h = [r[0] for r in con.execute("DESCRIBE staging.src_body").fetchall()]
    src_stale = [c for c in SRC_COLS if c not in _h]
if have_src and REUSE and not src_stale:
    n2 = table_count(con, 'staging.src_body')
    print(f"\nPHASE 1  SKIPPED, reusing staging.src_body ({n2:,} rows)", flush=True)
else:
  if src_stale:
      print(f"\n  staging.src_body predates {src_stale} -- REBUILDING it. This is the "
            f"569.7M x 197.6M join and is the slowest step in the pipeline; reusing the "
            f"old table would silently leave those columns NULL.", flush=True)
  print(f"\nPHASE 1  staging body dumps ({'ALL' if LOAD_ALL else f'~{LIMIT} sample'})...",
      flush=True)
  con.execute(f"""
CREATE OR REPLACE TABLE staging.src_body AS
SELECT g.system_id, g.sys_name, b.name AS body_name,
       lower(b.type) AS body_type, b.sub_type,
       coalesce(b.main_star, false) AS is_primary, 'spansh' AS source,
       b.solar_masses, b.earth_masses,
       b.terraforming_state = 'Terraformable' AS is_terraformable
FROM {SRC_SPANSH} b
JOIN staging.sys_bridge g ON g.system_id64 = b.system_id64
WHERE b.name IS NOT NULL {SAMPLE}
""")
  n0 = table_count(con, 'staging.src_body')
  print(f"  spansh                      {n0:>14,}", flush=True)

  con.execute(f"""
INSERT INTO staging.src_body
SELECT g.system_id, g.sys_name, b.name, lower(b.type), b.subType,
       coalesce(b.isMainStar, false), 'edsm',
       b.solarMasses, b.earthMasses, b.terraformingState = 'Terraformable'
FROM {SRC_EDSM} b
JOIN staging.sys_bridge g ON g.system_id64 = b.systemId64
WHERE b.name IS NOT NULL {SAMPLE}
  AND NOT EXISTS (SELECT 1 FROM staging.src_body s
                  WHERE s.system_id = g.system_id AND s.body_name = b.name)
""")
  n1 = table_count(con, 'staging.src_body')
  print(f"  + edsm  (7-day slice)       {n1 - n0:>14,}", flush=True)

  con.execute(f"""
INSERT INTO staging.src_body
SELECT g.system_id, g.sys_name, b.name, 'planet', b.subType, false, 'edastro',
       NULL, b.earthMasses, b.terraformingState = 'Terraformable'
FROM {SRC_EDASTRO} b
JOIN staging.sys_bridge g ON g.system_id64 = b.systemId64
WHERE b.name IS NOT NULL {SAMPLE}
  AND NOT EXISTS (SELECT 1 FROM staging.src_body s
                  WHERE s.system_id = g.system_id AND s.body_name = b.name)
""")
  n2 = table_count(con, 'staging.src_body')
  print(f"  + edastro (7-day slice)     {n2 - n1:>14,}", flush=True)

print("\nPHASE 1b EDAstro FULL catalogues (not slices)...", flush=True)
nb0 = table_count(con, 'staging.src_body')

con.execute("""
CREATE OR REPLACE TABLE staging.sys_name AS
SELECT k.system_id,
       CASE WHEN s.sector IS NULL THEN k.system_in_sector
            ELSE s.sector || ' ' || k.system_in_sector END AS full_name
FROM system_known k LEFT JOIN sector s ON s.sector_id = k.sector_id""")

con.execute(f"""
INSERT INTO staging.src_body
SELECT m.system_id, m.full_name, k.name, 'star', k.star_type,
       coalesce(k.is_main_star, false), 'edastro_rare', NULL, NULL, NULL
FROM edastro_known_rare k
JOIN staging.sys_name m ON m.full_name = coalesce(nullif(
       regexp_extract(k.name, '^(.*[A-Z][A-Z]-[A-Z] [a-h][0-9]*(-[0-9]+)?)', 1), ''), k.name)
WHERE k.name IS NOT NULL {SAMPLE.replace('b.name', 'k.name')}
  AND NOT EXISTS (SELECT 1 FROM staging.src_body s
                  WHERE s.system_id = m.system_id AND s.body_name = k.name)
""")
nb1 = table_count(con, 'staging.src_body')
print(f"  + edastro BH/WR (FULL)      {nb1 - nb0:>14,}", flush=True)

con.execute(f"""
INSERT INTO staging.src_body
SELECT g.system_id, n.system_name, n.body_name, 'star', 'Neutron Star',
       coalesce(n.is_arrival_star, false), 'edastro_neutron', NULL, NULL, NULL
FROM edastro_neutron_star n
JOIN staging.sys_bridge g ON g.system_id64 = n.system_id64
WHERE n.body_name IS NOT NULL {SAMPLE.replace('b.name', 'n.body_name')}
  AND NOT EXISTS (SELECT 1 FROM staging.src_body s
                  WHERE s.system_id = g.system_id AND s.body_name = n.body_name)
""")
nb2 = table_count(con, 'staging.src_body')
print(f"  + edastro neutron (FULL)    {nb2 - nb1:>14,}", flush=True)
print(f"  staged bodies               {nb2:>14,}", flush=True)

print("\nPHASE 2  staging discovery timestamps...", flush=True)

con.execute("""
CREATE OR REPLACE TABLE staging.sb_disc AS
SELECT s.system_id,
       CASE WHEN starts_with(s.body_name, s.sys_name)
            THEN trim(substr(s.body_name, length(s.sys_name) + 1))
            ELSE s.body_name END                              AS system_body,
       min(TRY_CAST(k.discovered_at AS TIMESTAMP))             AS discovered_time
FROM edastro_known_rare k
JOIN staging.src_body s ON s.body_name = k.name
WHERE k.discovered_at IS NOT NULL
GROUP BY 1, 2
""")
ndt = table_count(con, 'staging.sb_disc')
print(f"  discovery timestamps       {ndt:>14,}  (BH/WR only -- nothing else records it)", flush=True)

print("\nPHASE 2b resolving ambiguous primaries...", flush=True)
con.execute("""
CREATE OR REPLACE TABLE staging.sb_ambig AS
WITH prim AS (
  SELECT s.system_id, s.body_name,
         CASE WHEN starts_with(s.body_name, s.sys_name)
              THEN trim(substr(s.body_name, length(s.sys_name) + 1))
              ELSE s.body_name END AS system_body
  FROM staging.src_body s
  WHERE s.is_primary
)
SELECT system_id, body_name, system_body FROM prim
WHERE system_id IN (SELECT system_id FROM prim
                    GROUP BY 1 HAVING count(DISTINCT system_body) > 1)
""")
namb = con.execute("SELECT count(DISTINCT system_id) FROM staging.sb_ambig").fetchone()[0]
print(f"  systems with >1 primary    {namb:>14,}", flush=True)

con.execute("""
CREATE OR REPLACE TABLE staging.sb_primary AS
SELECT system_id, system_body FROM (
  SELECT a.system_id, a.system_body,
         row_number() OVER (
           PARTITION BY a.system_id ORDER BY
             (b.dist_to_arrival_ls IS NULL),                                  -- 1
             b.dist_to_arrival_ls                          NULLS LAST,
             (b.sub_type IS NULL OR coalesce(b.solar_masses, 0) <= 0),        -- 2
             b.body_id                                     NULLS LAST,        -- 3
             a.system_body
         ) AS rn
  FROM staging.sb_ambig a
  JOIN staging.sys_bridge g ON g.system_id = a.system_id
  LEFT JOIN spansh_body b
    ON b.system_id64 = g.system_id64 AND b.name = a.body_name
) WHERE rn = 1
""")
nres = table_count(con, 'staging.sb_primary')
print(f"  resolved to one winner     {nres:>14,}"
      f"{'' if nres == namb else '   <== SHORTFALL, some system got no winner'}",
      flush=True)

if STAGE_ONLY:
    print("\n  --stage-only: staging.sb_dedup built, nothing merged.", flush=True)
    con.close()
    raise SystemExit

DEDUP_COLS = ["system_id", "system_body", "body_id", "is_primary", "solar_masses",
              "earth_masses", "is_terraformable", "source"]
have_dedup = con.execute("""SELECT count(*) FROM duckdb_tables()
    WHERE schema_name='staging' AND table_name='sb_dedup'""").fetchone()[0]
if have_dedup:
    _h = [r[0] for r in con.execute("DESCRIBE staging.sb_dedup").fetchall()]
    if [c for c in DEDUP_COLS if c not in _h]:
        print(f"\n  staging.sb_dedup predates the mass columns -- DROPPING it; the merge "
              f"will strip and dedupe per bucket instead.", flush=True)
        con.execute("DROP TABLE staging.sb_dedup")
        have_dedup = 0
staged_bodies = table_count(con, 'staging.src_body')
BUCKETS = BUCKET_ARG or (BUCKETS_DELTA if staged_bodies <= DELTA_MAX else BUCKETS_FULL)
print(f"\n  {staged_bodies:,} staged body row(s) -> {BUCKETS} bucket(s)", flush=True)

if have_dedup:
    nsd = table_count(con, 'staging.sb_dedup')
    print(f"\nPHASE 3  merging in {BUCKETS} bucket(s), reusing staging.sb_dedup "
          f"({nsd:,} rows)...", flush=True)
    SRC = """SELECT system_id, system_body, body_id, is_primary,
                    solar_masses, earth_masses, is_terraformable, source
             FROM staging.sb_dedup"""
else:
    print(f"\nPHASE 3  merging in {BUCKETS} bucket(s) (strip + dedupe per bucket)...",
          flush=True)
    SRC = """
      WITH stripped AS (
        SELECT s.system_id,
               CASE WHEN starts_with(s.body_name, s.sys_name)
                    THEN trim(substr(s.body_name, length(s.sys_name) + 1))
                    ELSE s.body_name END AS system_body,
               bo.body_id, s.is_primary,
               s.solar_masses, s.earth_masses, s.is_terraformable, s.source
        FROM staging.src_body s
        LEFT JOIN body bo ON bo.body = s.sub_type AND bo.type = s.body_type
        WHERE s.system_id % {BUCKETS} = {b}
      )
      SELECT system_id, system_body, max(body_id) AS body_id,
             bool_or(is_primary) AS is_primary,
             max(solar_masses) AS solar_masses, max(earth_masses) AS earth_masses,
             bool_or(is_terraformable) AS is_terraformable,
             min(CASE source WHEN 'spansh' THEN '1spansh' WHEN 'edsm' THEN '2edsm'
                             WHEN 'edastro' THEN '3edastro'
                             WHEN 'edastro_neutron' THEN '4edastro_neutron'
                             ELSE '5edastro_rare' END)[2:] AS source
      FROM stripped GROUP BY 1, 2"""

_MASS_PRESENT = (f"SELECT count(*) FROM {TABLE} WHERE solar_masses IS NOT NULL "
                 f"OR earth_masses IS NOT NULL OR is_terraformable IS NOT NULL")
before = table_count(con, TABLE)
mass_before = con.execute(_MASS_PRESENT).fetchone()[0]
for b in range(BUCKETS):
    src = SRC.format(BUCKETS=BUCKETS, b=b) if "{BUCKETS}" in SRC else SRC
    bucket_filter = "" if "{BUCKETS}" in SRC else f"AND d.system_id % {BUCKETS} = {b}"
    con.execute(f"""
    INSERT INTO {TABLE} (system_body_id, system_id, body_id, system_body, is_primary,
                         discovered_time, solar_masses, earth_masses, is_terraformable,
                         source)
    SELECT (SELECT coalesce(max(system_body_id), 0) FROM {TABLE})
             + row_number() OVER (ORDER BY d.system_id, d.system_body),
           d.system_id, d.body_id, d.system_body, d.is_primary, t.discovered_time,
           d.solar_masses, d.earth_masses, d.is_terraformable, d.source
    FROM ({src}) d
    LEFT JOIN staging.sb_disc t
      ON t.system_id = d.system_id AND t.system_body = d.system_body
    WHERE NOT EXISTS (SELECT 1 FROM {TABLE} k
                      WHERE k.system_id = d.system_id
                        AND k.system_body = d.system_body)
      {bucket_filter}
    """)
    con.execute(f"""
    UPDATE {TABLE} SET solar_masses = d.solar_masses, earth_masses = d.earth_masses,
                       is_terraformable = d.is_terraformable, source = d.source
    FROM ({src}) d
    WHERE {TABLE}.system_id = d.system_id AND {TABLE}.system_body = d.system_body
      AND ({TABLE}.solar_masses     IS DISTINCT FROM d.solar_masses
        OR {TABLE}.earth_masses     IS DISTINCT FROM d.earth_masses
        OR {TABLE}.is_terraformable IS DISTINCT FROM d.is_terraformable
        OR {TABLE}.source           IS DISTINCT FROM d.source)
      {bucket_filter}
    """)
    if (b + 1) % max(1, BUCKETS // 8) == 0:
        now = table_count(con, TABLE)
        nm = con.execute(_MASS_PRESENT).fetchone()[0]
        print(f"    bucket {b+1:>4}/{BUCKETS}   {now:,} rows   {nm:,} with mass",
              flush=True)

after = table_count(con, TABLE)
mass_after = con.execute(_MASS_PRESENT).fetchone()[0]
print(f"\n  mass backfill: {mass_after - mass_before:,} row(s) gained mass/terraform "
      f"data ({mass_before:,} -> {mass_after:,})", flush=True)

_D = f"""WHERE {TABLE}.system_id = p.system_id AND {TABLE}.is_primary
  AND {TABLE}.system_body IS DISTINCT FROM p.system_body"""
demoted = count_then_update(con,
    f"SELECT count(*) FROM {TABLE}, staging.sb_primary p {_D}",
    f"UPDATE {TABLE} SET is_primary = false FROM staging.sb_primary p {_D}")
_P = f"""WHERE {TABLE}.system_id = p.system_id
  AND {TABLE}.system_body = p.system_body AND NOT {TABLE}.is_primary"""
promoted = count_then_update(con,
    f"SELECT count(*) FROM {TABLE}, staging.sb_primary p {_P}",
    f"UPDATE {TABLE} SET is_primary = true FROM staging.sb_primary p {_P}")
print(f"\n  primary cascade: {demoted:,} demoted, {promoted:,} promoted", flush=True)

CATALOGUE_ONLY = "('edastro_rare','edastro_neutron','canonn_codex')"
con.execute(f"""
CREATE OR REPLACE TABLE staging.sb_dual AS
WITH dual AS (
  SELECT system_id FROM {TABLE} WHERE is_primary GROUP BY 1 HAVING count(*) > 1
)
SELECT b.system_id, b.system_body_id,
       row_number() OVER (PARTITION BY b.system_id ORDER BY
           (b.system_body <> '') ASC,
           (b.source IN {CATALOGUE_ONLY}) ASC,
           (b.solar_masses IS NULL) ASC,
           b.system_body_id ASC) AS rn
FROM {TABLE} b JOIN dual d USING (system_id)
WHERE b.is_primary""")
nd = con.execute("SELECT count(DISTINCT system_id) FROM staging.sb_dual").fetchone()[0]
if nd:
    _S = f"""WHERE {TABLE}.system_body_id = d.system_body_id AND d.rn > 1
               AND {TABLE}.is_primary"""
    swept = count_then_update(con,
        f"SELECT count(*) FROM {TABLE}, staging.sb_dual d {_S}",
        f"UPDATE {TABLE} SET is_primary = false FROM staging.sb_dual d {_S}")
    print(f"  global sweep: {nd:,} system(s) held >1 primary after the merge, "
          f"{swept:,} row(s) demoted", flush=True)
else:
    print("  global sweep: no system holds >1 primary (ok)", flush=True)

report_merge(TABLE, before, after, after - before, demoted + promoted, [])
print(f"  {has_primary_key(con, TABLE)}", flush=True)

print(f"\n  {'coverage in ' + TABLE:<36}{'n':>14}{'%':>8}", flush=True)
tot = max(after, 1)
for lab_, w in (("body_id known", "body_id IS NOT NULL"),
                ("is_primary", "is_primary"),
                ("discovered_time", "discovered_time IS NOT NULL"),
                ("empty designation (primary star)", "system_body = ''"),
                ("solar_masses (stars)", "solar_masses IS NOT NULL"),
                ("earth_masses (planets)", "earth_masses IS NOT NULL"),
                ("is_terraformable known", "is_terraformable IS NOT NULL"),
                ("is_terraformable TRUE", "is_terraformable"),
                ("source known", "source IS NOT NULL"),
                ("CATALOGUE-ONLY (not a scan)",
                 "source IN ('edastro_rare','edastro_neutron')")):
    c = con.execute(f"SELECT count(*) FROM {TABLE} WHERE {w}").fetchone()[0]
    print(f"  {lab_:<36}{c:>14,}{100.0*c/tot:>7.2f}%", flush=True)

bad = con.execute(f"""
SELECT count(*) FROM (SELECT system_id FROM {TABLE} WHERE is_primary
                      GROUP BY 1 HAVING count(*) > 1)""").fetchone()[0]
mismatch = con.execute(f"""
SELECT count(*) FROM {TABLE} sb JOIN system_known sk USING (system_id)
WHERE sb.is_primary AND sk.primary_star_body_id IS NOT NULL
  AND sb.body_id IS DISTINCT FROM sk.primary_star_body_id""").fetchone()[0]
print(f"\n  CONSISTENCY (not enforceable in DDL):", flush=True)
print(f"\n  {'source':<24}{'bodies':>16}")
for r in con.execute(f"""SELECT coalesce(source,'(none)'), count(*) FROM {TABLE}
                         GROUP BY 1 ORDER BY 2 DESC""").fetchall():
    print(f"  {r[0]:<24}{r[1]:>16,}")

print(f"\n    systems with >1 is_primary row      {bad:>12,}"
      f"  {'<== BROKEN' if bad else '(ok)'}")
print(f"    is_primary disagrees with           {mismatch:>12,}"
      f"  {'<== CHECK' if mismatch else '(ok)'}")
print(f"      system_known.primary_star_body_id", flush=True)
con.close()
print("\nDONE_BUILD_SYSTEM_BODY", flush=True)

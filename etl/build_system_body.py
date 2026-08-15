"""Build `system_body` -- one row per body in a system.

Same three-phase shape as etl/build_system_known.py, all intermediates in `staging`:

  1. STAGE the body dumps into staging.src_body, one row per (system, body designation),
     each source contributing only bodies the earlier ones lack:
       spansh   spansh_body          569,697,301   the only body source at galaxy scale
       edsm     edsm_celestial_body   +up to 2.5M   *** 7-DAY SLICE, not a catalogue ***
       edastro  edastro_planet        +up to 2.7M   *** 7-DAY SLICE *** , planets only
     The two slices are included because the user asked for all three feeds, but they add
     little: both are overwhelmingly subsets of Spansh.

  2. RESOLVE to system_known.system_id and body.body_id, and derive the designation.

  3. MERGE: insert bodies we do not have, matched on (system_id, system_body).

THE BRIDGE. system_known deliberately does not store the game's id64, so bodies cannot
join to it directly. staging.sk_ready (left behind by build_system_known.py) carries BOTH
system_id64 and the natural key, so it is the bridge: sk_ready JOIN system_known on
(sector_id, "system") gives id64 -> system_id. Run build_system_known.py first or there
is nothing to join to, and the system_id foreign key will reject every row.

DESIGNATION. system_body is the body name with the system name stripped: 'Blae Hypue
EB-N d7-0 A' -> 'A'; Sol's bodies are 'Mercury', 'Earth', 'Moon'. The primary star's name
usually EQUALS the system name, so its designation is the EMPTY STRING -- kept as '', not
NULL. About 1 body in 200,000 does not start with its system name; those keep the full
name rather than being silently mangled.

MASS. solar_masses / earth_masses / is_terraformable are carried through from the source
dumps so that SCAN VALUE is computable from this table plus `body` alone, without going
back to the 569.7M-row spansh_body. The exploration formula needs mass -- it is not a
refinement:
    planets:  base = max(k + k * earth_masses^0.2 * 0.56591828, 500)
    stars:    base = k + solar_masses * k / 66.25
with k = body.cr_value, or body.cr_value_terraformable where is_terraformable. Mass is
worth ~57% of an Earth-like's value and only ~1.5% of an ordinary star's, so dropping it
would understate planets badly and stars barely.

PRIMARY STAR. is_primary comes from Spansh's main_star flag, which is not unique: 241
systems have two bodies flagged. Phase 2b picks one with a fixed cascade -- nearest
dist_to_arrival_ls, then the more complete record, then the lowest Spansh body_id -- and
a post-merge UPDATE applies it, so the invariant holds for rows earlier runs wrote too.

Usage:  python etl/build_system_body.py                  # DDL + comments only
        python etl/build_system_body.py --limit 200000    # sample
        python etl/build_system_body.py --all             # full ~570M load
        python etl/build_system_body.py --all --rebuild-staging  # redo the join
        python etl/build_system_body.py --clean-staging
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common.db import (connect, comment_file, apply_comment_file, report_merge,
                       has_primary_key, count_then_update, ensure_columns)

TABLE = "system_body"
BUCKETS = 128        # bodies outnumber systems ~3:1, so more buckets than system_known

LOAD_ALL = "--all" in sys.argv
STAGE_ONLY = "--stage-only" in sys.argv
CLEAN = "--clean-staging" in sys.argv
# staging.src_body costs a 569.7M x 197.6M join to build; reuse it by default.
REUSE = "--rebuild-staging" not in sys.argv
LIMIT = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None

con = connect(memory_limit="20GB", threads=14)
con.execute("CREATE SCHEMA IF NOT EXISTS staging")

if CLEAN:
    for (t,) in con.execute("""SELECT table_name FROM duckdb_tables()
        WHERE schema_name='staging' AND table_name LIKE '%body%'""").fetchall():
        n = con.execute(f"SELECT count(*) FROM staging.{t}").fetchone()[0]
        con.execute(f"DROP TABLE staging.{t}")
        print(f"  dropped staging.{t} ({n:,} rows)", flush=True)
    if not (LIMIT or LOAD_ALL or STAGE_ONLY):
        con.close()
        raise SystemExit("staging cleaned")

# ---------------------------------------------------------------------- DDL ---
# CORE columns carry the PRIMARY KEY, the UNIQUE and both FOREIGN KEYs, so they can only
# come from the CREATE -- a table missing one needs a create-copy-swap, not an ALTER.
CORE = ["system_body_id", "system_id", "body_id", "system_body", "is_primary",
        "discovered_time"]
# EXTRA columns are plain nullable attributes and ARE ALTERable, so an existing 570M-row
# table migrates in place. Order here must match the CREATE below: ALTER can only append,
# and a migrated database has to end up the same shape as a freshly created one.
EXTRA = {"solar_masses": "DOUBLE", "earth_masses": "DOUBLE",
         "is_terraformable": "BOOLEAN"}
existed = con.execute("""SELECT count(*) FROM duckdb_tables()
                         WHERE schema_name='main' AND table_name=?""",
                      [TABLE]).fetchone()[0]
if existed:
    have = [r[0] for r in con.execute(f"DESCRIBE {TABLE}").fetchall()]
    missing_core = [c for c in CORE if c not in have]
    if missing_core:
        n = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
        if n == 0:
            print(f"  schema differs, table EMPTY -- rebuilding for {missing_core}",
                  flush=True)
            con.execute(f"DROP TABLE {TABLE}")
            existed = 0
        else:
            sys.exit(f"{TABLE} has {n:,} rows and is missing {missing_core}. DuckDB "
                     f"cannot ALTER in a FOREIGN KEY -- needs a create-copy-swap "
                     f"migration.")
con.execute(f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    system_body_id BIGINT  NOT NULL PRIMARY KEY,
    system_id      BIGINT  NOT NULL,
    body_id        INTEGER,
    system_body    VARCHAR NOT NULL,
    is_primary     BOOLEAN NOT NULL,
    discovered_time TIMESTAMP,
    solar_masses    DOUBLE,
    earth_masses    DOUBLE,
    is_terraformable BOOLEAN,
    UNIQUE (system_id, system_body),
    FOREIGN KEY (system_id) REFERENCES system_known (system_id),
    FOREIGN KEY (body_id)   REFERENCES body (body_id)
)""")
if existed:
    ensure_columns(con, TABLE, EXTRA)
print(f"{TABLE}: {'exists' if existed else 'CREATED'}, "
      f"{con.execute(f'SELECT count(*) FROM {TABLE}').fetchone()[0]:,} row(s)")
apply_comment_file(con, comment_file(TABLE))

if not (LIMIT or LOAD_ALL or STAGE_ONLY):
    print("\n  no --limit / --all / --stage-only: DDL and comments only.", flush=True)
    con.close()
    raise SystemExit

# ------------------------------------------------------------------ bridge ---
have_ready = con.execute("""SELECT count(*) FROM duckdb_tables()
    WHERE schema_name='staging' AND table_name='sk_ready'""").fetchone()[0]
if not have_ready:
    sys.exit("staging.sk_ready is missing -- it is the id64 -> system_id bridge.\n"
             "Run: python etl/build_system_known.py --all")
have_bridge = con.execute("""SELECT count(*) FROM duckdb_tables()
    WHERE schema_name='staging' AND table_name='sys_bridge'""").fetchone()[0]
have_src0 = con.execute("""SELECT count(*) FROM duckdb_tables()
    WHERE schema_name='staging' AND table_name='src_body'""").fetchone()[0]
if have_bridge and have_src0 and REUSE:
    nb = con.execute("SELECT count(*) FROM staging.sys_bridge").fetchone()[0]
    print(f"\nbridge reused ({nb:,} rows) -- only Phase 1 needs it", flush=True)
else:
  print("\nbuilding the id64 -> system_id bridge...", flush=True)
  con.execute(f"""
CREATE OR REPLACE TABLE staging.sys_bridge AS
SELECT r.system_id64, k.system_id, r.name AS sys_name
FROM staging.sk_ready r
JOIN system_known k
  ON k.sector_id = r.sector_id AND k."system" = r."system"
WHERE r.system_id64 IS NOT NULL
""")
  nb = con.execute("SELECT count(*) FROM staging.sys_bridge").fetchone()[0]
  nk = con.execute("SELECT count(*) FROM system_known").fetchone()[0]
  print(f"  bridged {nb:,} of {nk:,} system_known rows "
        f"({100.0*nb/max(nk,1):.2f}%; the rest have no id64 -- EDAstro-sourced)",
        flush=True)

SAMPLE = "" if LOAD_ALL else \
    f"AND hash(b.name) % {max(1, 600_000_000 // max(LIMIT or 1, 1))} = 0"

# --------------------------------------------------- PHASE 1: stage bodies ---
# Reusable on purpose: this join (569.7M bodies x 197.6M systems) is the single most
# expensive statement in the pipeline, so a restart should not repeat it.
#
# *** The reuse check is COLUMN-AWARE, not just existence-aware. *** A staging table
# built before the mass columns existed still has the right row count and would sail
# through an existence check, then feed NULL mass into every row while the merge
# reported success -- the same silent-empty-column failure ETL.md documents for `<>`.
# A stale table is rebuilt instead, expensive or not.
SRC_COLS = ["system_id", "sys_name", "body_name", "body_type", "sub_type", "is_primary",
            "source", "solar_masses", "earth_masses", "is_terraformable"]
have_src = con.execute("""SELECT count(*) FROM duckdb_tables()
    WHERE schema_name='staging' AND table_name='src_body'""").fetchone()[0]
src_stale = []
if have_src:
    _h = [r[0] for r in con.execute("DESCRIBE staging.src_body").fetchall()]
    src_stale = [c for c in SRC_COLS if c not in _h]
if have_src and REUSE and not src_stale:
    n2 = con.execute("SELECT count(*) FROM staging.src_body").fetchone()[0]
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
FROM spansh_body b
JOIN staging.sys_bridge g ON g.system_id64 = b.system_id64
WHERE b.name IS NOT NULL {SAMPLE}
""")
  n0 = con.execute("SELECT count(*) FROM staging.src_body").fetchone()[0]
  print(f"  spansh                      {n0:>14,}", flush=True)

  # EDSM and EDAstro are 7-DAY SLICES. They are NOT redundant: together they added
  # 310,783 bodies Spansh lacks (301,519 + 9,264) -- only 0.05%, but real.
  con.execute(f"""
INSERT INTO staging.src_body
SELECT g.system_id, g.sys_name, b.name, lower(b.type), b.subType,
       coalesce(b.isMainStar, false), 'edsm',
       b.solarMasses, b.earthMasses, b.terraformingState = 'Terraformable'
FROM edsm_celestial_body b
JOIN staging.sys_bridge g ON g.system_id64 = b.systemId64
WHERE b.name IS NOT NULL {SAMPLE}
  AND NOT EXISTS (SELECT 1 FROM staging.src_body s
                  WHERE s.system_id = g.system_id AND s.body_name = b.name)
""")
  n1 = con.execute("SELECT count(*) FROM staging.src_body").fetchone()[0]
  print(f"  + edsm  (7-day slice)       {n1 - n0:>14,}", flush=True)

  con.execute(f"""
INSERT INTO staging.src_body
SELECT g.system_id, g.sys_name, b.name, 'planet', b.subType, false, 'edastro',
       NULL, b.earthMasses, b.terraformingState = 'Terraformable'
FROM edastro_planet b
JOIN staging.sys_bridge g ON g.system_id64 = b.systemId64
WHERE b.name IS NOT NULL {SAMPLE}
  AND NOT EXISTS (SELECT 1 FROM staging.src_body s
                  WHERE s.system_id = g.system_id AND s.body_name = b.name)
""")
  n2 = con.execute("SELECT count(*) FROM staging.src_body").fetchone()[0]
  print(f"  + edastro (7-day slice)     {n2 - n1:>14,}", flush=True)
  print(f"  staged bodies               {n2:>14,}", flush=True)

# ------------------------------------------------- PHASE 2: resolve ----------
# Only the discovery timestamps are staged here. Designation-stripping and the dedupe
# aggregate used to be two full ~570M-row passes at this point; both are now done inside
# each Phase 3 bucket instead -- see the note at the top of Phase 3.
print("\nPHASE 2  staging discovery timestamps...", flush=True)

# The ONLY genuine source is edastro_known_rare (BH/WR, 101,943 rows with a date).
# spansh_body.update_time is LAST UPDATE, not discovery, and is deliberately unused.
# EQUI-JOIN ONLY. An earlier version matched
#   ON k.name = g.sys_name OR starts_with(k.name, g.sys_name || ' ')
# which DuckDB cannot hash: it became a nested loop of 516,714 x 197,560,673 ~= 1e14
# comparisons and never finished. edastro_known_rare.name IS a body name, and
# staging.src_body already holds (system_id, sys_name, body_name), so joining on body_name
# is a hash join AND hands us sys_name for the designation.
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
ndt = con.execute("SELECT count(*) FROM staging.sb_disc").fetchone()[0]
print(f"  discovery timestamps       {ndt:>14,}  (BH/WR only -- nothing else records it)", flush=True)

# ------------------------------------ PHASE 2b: resolve ambiguous primaries ---
# Spansh flags MORE THAN ONE body as main_star in a small number of systems (324 in the
# raw dump, 241 after our dedupe). bool_or(is_primary) alone therefore leaves two rows
# both claiming to be the primary, breaking the one-primary-per-system invariant that
# the DDL cannot express. Resolve with a fixed cascade, most-principled step first:
#
#   1. MIN dist_to_arrival_ls  -- the arrival star IS the primary, by definition. A NULL
#                                 distance always loses. Decided 92 of the 241.
#   2. COMPLETENESS            -- prefer a row having a sub_type AND solar_masses > 0.
#                                 The loser is a stub record: mass 0.00, spectral class
#                                 truncated to a bare letter, sometimes no type/dist/mass
#                                 at all. Decided 77 more.
#   3. LOWEST spansh body_id   -- arbitrary but DETERMINISTIC, for the last 72. In 53 of
#                                 them the two rows are ONE star recorded under two names
#                                 in a hand-named catalogue system ('NGC 2168 MMS 277' and
#                                 'NGC 2168 MMS 277 A', identical sub_type and mass); both
#                                 resolve to the SAME body_id, only the designation
#                                 differs, and body_id 0 is the bare name. The other 19
#                                 are genuine twins -- different stars, both complete,
#                                 both at 0.0 ls -- where the data supports no winner at
#                                 all and a stable pick beats an arbitrary one.
#
# Only ambiguous systems are materialised, so this stays tiny however large the load.
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

# LEFT JOIN on purpose: a primary contributed by the EDSM/EDAstro slices has no
# spansh_body row, so it has no attributes to judge and must rank LAST rather than
# vanish -- otherwise a system whose primaries are all slice-sourced would get no
# winner and stay broken silently.
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
nres = con.execute("SELECT count(*) FROM staging.sb_primary").fetchone()[0]
print(f"  resolved to one winner     {nres:>14,}"
      f"{'' if nres == namb else '   <== SHORTFALL, some system got no winner'}",
      flush=True)

if STAGE_ONLY:
    print("\n  --stage-only: staging.sb_dedup built, nothing merged.", flush=True)
    con.close()
    raise SystemExit

# ---------------------------------------------------------- PHASE 3: merge ---
# A completed staging.sb_dedup from an earlier run is reused rather than recomputed --
# that pass costs a full 570M-row aggregate. Otherwise strip + dedupe happen INSIDE each
# bucket, which is the better shape for a clean run: system_id is part of the dedupe key,
# so no group can span a `system_id % BUCKETS` bucket, and nothing 570M-row wide is ever
# materialised.
# Column-aware for the same reason Phase 1 is: a sb_dedup built before the mass columns
# has the right row count but cannot supply them.
DEDUP_COLS = ["system_id", "system_body", "body_id", "is_primary", "solar_masses",
              "earth_masses", "is_terraformable"]
have_dedup = con.execute("""SELECT count(*) FROM duckdb_tables()
    WHERE schema_name='staging' AND table_name='sb_dedup'""").fetchone()[0]
if have_dedup:
    _h = [r[0] for r in con.execute("DESCRIBE staging.sb_dedup").fetchall()]
    if [c for c in DEDUP_COLS if c not in _h]:
        print(f"\n  staging.sb_dedup predates the mass columns -- DROPPING it; the merge "
              f"will strip and dedupe per bucket instead.", flush=True)
        con.execute("DROP TABLE staging.sb_dedup")
        have_dedup = 0
if have_dedup:
    nsd = con.execute("SELECT count(*) FROM staging.sb_dedup").fetchone()[0]
    print(f"\nPHASE 3  merging in {BUCKETS} bucket(s), reusing staging.sb_dedup "
          f"({nsd:,} rows)...", flush=True)
    SRC = """SELECT system_id, system_body, body_id, is_primary,
                    solar_masses, earth_masses, is_terraformable
             FROM staging.sb_dedup"""
else:
    print(f"\nPHASE 3  merging in {BUCKETS} bucket(s) (strip + dedupe per bucket)...",
          flush=True)
    # starts_with guard: ~1 body in 200,000 does not carry its system name as a prefix,
    # and a blind substr() would corrupt those; they keep the full name.
    SRC = """
      WITH stripped AS (
        SELECT s.system_id,
               CASE WHEN starts_with(s.body_name, s.sys_name)
                    THEN trim(substr(s.body_name, length(s.sys_name) + 1))
                    ELSE s.body_name END AS system_body,
               bo.body_id, s.is_primary,
               s.solar_masses, s.earth_masses, s.is_terraformable
        FROM staging.src_body s
        LEFT JOIN body bo ON bo.body = s.sub_type AND bo.type = s.body_type
        WHERE s.system_id % {BUCKETS} = {b}
      )
      SELECT system_id, system_body, max(body_id) AS body_id,
             bool_or(is_primary) AS is_primary,
             -- max()/bool_or() for the same reason body_id uses max(): ~95 bodies
             -- galaxy-wide collide on (system_id, designation) and collapse into one row.
             max(solar_masses) AS solar_masses, max(earth_masses) AS earth_masses,
             bool_or(is_terraformable) AS is_terraformable
      FROM stripped GROUP BY 1, 2"""

_MASS_PRESENT = (f"SELECT count(*) FROM {TABLE} WHERE solar_masses IS NOT NULL "
                 f"OR earth_masses IS NOT NULL OR is_terraformable IS NOT NULL")
before = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
mass_before = con.execute(_MASS_PRESENT).fetchone()[0]
for b in range(BUCKETS):
    src = SRC.format(BUCKETS=BUCKETS, b=b) if "{BUCKETS}" in SRC else SRC
    bucket_filter = "" if "{BUCKETS}" in SRC else f"AND d.system_id % {BUCKETS} = {b}"
    con.execute(f"""
    INSERT INTO {TABLE} (system_body_id, system_id, body_id, system_body, is_primary,
                         discovered_time, solar_masses, earth_masses, is_terraformable)
    SELECT (SELECT coalesce(max(system_body_id), 0) FROM {TABLE})
             + row_number() OVER (ORDER BY d.system_id, d.system_body),
           d.system_id, d.body_id, d.system_body, d.is_primary, t.discovered_time,
           d.solar_masses, d.earth_masses, d.is_terraformable
    FROM ({src}) d
    LEFT JOIN staging.sb_disc t
      ON t.system_id = d.system_id AND t.system_body = d.system_body
    WHERE NOT EXISTS (SELECT 1 FROM {TABLE} k
                      WHERE k.system_id = d.system_id
                        AND k.system_body = d.system_body)
      {bucket_filter}
    """)
    # BACKFILL. The INSERT above only fires WHERE NOT EXISTS, so on a database that
    # already holds the rows it can never supply the mass columns -- this UPDATE is what
    # actually fills them, exactly as the primary cascade fills is_primary.
    # IS DISTINCT FROM, never <>: the columns are NULL on every pre-migration row, and
    # `NULL <> 1.5` is NULL, so a <> test would match nothing and silently backfill
    # nothing. It also makes re-runs free -- a row already carrying the right values is
    # not rewritten, which matters when the alternative is rewriting 570M rows.
    con.execute(f"""
    UPDATE {TABLE} SET solar_masses = d.solar_masses, earth_masses = d.earth_masses,
                       is_terraformable = d.is_terraformable
    FROM ({src}) d
    WHERE {TABLE}.system_id = d.system_id AND {TABLE}.system_body = d.system_body
      AND ({TABLE}.solar_masses     IS DISTINCT FROM d.solar_masses
        OR {TABLE}.earth_masses     IS DISTINCT FROM d.earth_masses
        OR {TABLE}.is_terraformable IS DISTINCT FROM d.is_terraformable)
      {bucket_filter}
    """)
    if (b + 1) % 8 == 0:
        now = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
        nm = con.execute(_MASS_PRESENT).fetchone()[0]
        print(f"    bucket {b+1:>4}/{BUCKETS}   {now:,} rows   {nm:,} with mass",
              flush=True)

after = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
mass_after = con.execute(_MASS_PRESENT).fetchone()[0]
print(f"\n  mass backfill: {mass_after - mass_before:,} row(s) gained mass/terraform "
      f"data ({mass_before:,} -> {mass_after:,})", flush=True)

# Apply the Phase 2b cascade. This runs as an UPDATE rather than being folded into the
# bucket INSERT for two reasons: the INSERT only fires WHERE NOT EXISTS, so it can never
# correct a row an earlier run already wrote, and keeping it out of the 570M-row hot loop
# means the tiebreak cannot slow or destabilise the merge. It is idempotent -- a second
# run demotes and promotes nothing.
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
                ("is_terraformable TRUE", "is_terraformable")):
    c = con.execute(f"SELECT count(*) FROM {TABLE} WHERE {w}").fetchone()[0]
    print(f"  {lab_:<36}{c:>14,}{100.0*c/tot:>7.2f}%", flush=True)

# The invariant the DDL cannot enforce: exactly one primary per system, agreeing with
# system_known.primary_star_body_id.
bad = con.execute(f"""
SELECT count(*) FROM (SELECT system_id FROM {TABLE} WHERE is_primary
                      GROUP BY 1 HAVING count(*) > 1)""").fetchone()[0]
mismatch = con.execute(f"""
SELECT count(*) FROM {TABLE} sb JOIN system_known sk USING (system_id)
WHERE sb.is_primary AND sk.primary_star_body_id IS NOT NULL
  AND sb.body_id IS DISTINCT FROM sk.primary_star_body_id""").fetchone()[0]
print(f"\n  CONSISTENCY (not enforceable in DDL):", flush=True)
print(f"    systems with >1 is_primary row      {bad:>12,}"
      f"  {'<== BROKEN' if bad else '(ok)'}")
print(f"    is_primary disagrees with           {mismatch:>12,}"
      f"  {'<== CHECK' if mismatch else '(ok)'}")
print(f"      system_known.primary_star_body_id", flush=True)
con.close()
print("\nDONE_BUILD_SYSTEM_BODY", flush=True)

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (apply_comment_file, comment_file, connect, count_then_update,
                       has_primary_key, prepare_table, report_merge, table_count)

TABLE = "system_phenomenon"
BUILD = "--build" in sys.argv

con = connect(memory_limit="8GB")

prepare_table(con, TABLE, "canonn_codex_event + edsm_codex_entry")
if not has_primary_key(con, TABLE):
    print(f"  NOTE: {TABLE} predates its PRIMARY KEY declaration -- DuckDB has "
          f"no ALTER TABLE ADD PRIMARY KEY, so it stays unconstrained.")

if not BUILD:
    print("\n  no --build: DDL and comments only.", flush=True)
    con.close()
    raise SystemExit

if not con.execute("SELECT count(*) FROM system_known WHERE id64 IS NOT NULL"
                   ).fetchone()[0]:
    sys.exit("system_known.id64 is empty -- it is the id64 -> system_id mapping.\n"
             "Run: python etl/system_known/build.py --id64")

con.execute("CREATE SCHEMA IF NOT EXISTS staging")

print("classifying codex observations...", flush=True)
# The family classifier below is DUPLICATED in etl/poi/build.py rather than shared
# through common/; the two anomaly regexes already differ.
con.execute("""
CREATE OR REPLACE TABLE staging.ph_obs AS
WITH u AS (
    SELECT id64 AS system_id64, hud_category, english_name AS entry_name,
           TRY_CAST(reported_at AS TIMESTAMP) AS reported_at, 'canonn' AS source
    FROM canonn_codex_event
    UNION ALL
    SELECT systemId64, CAST(NULL AS VARCHAR), name,
           TRY_CAST(reportedOn AS TIMESTAMP), 'edsm'
    FROM edsm_codex_entry
)
SELECT system_id64, source, reported_at,
       CASE
         WHEN regexp_matches(lower(entry_name), 'bell|bulb|bullet|capsule|globe|gourd|parasol|reel|squid|torus|umbrella')
              AND lower(entry_name) LIKE '%mollusc%'                    THEN 'mollusc'
         WHEN lower(entry_name) LIKE '%tree%'
              OR lower(entry_name) LIKE '%void heart%'                  THEN 'plant'
         WHEN lower(entry_name) LIKE '%pod%'                            THEN 'seed_pod'
         WHEN regexp_matches(lower(entry_name), 'crystal|calcite plate|mineral sphere')
                                                                        THEN 'mineral_formation'
         WHEN lower(entry_name) LIKE '%lagrange%'                       THEN 'lagrange_cloud'
         WHEN regexp_matches(lower(entry_name), '\\b[eklpqt]-type\\b')
              OR lower(entry_name) LIKE '%anomaly%'                     THEN 'anomaly'
         ELSE NULL
       END AS nsp_family
FROM u
WHERE system_id64 IS NOT NULL
  AND (hud_category = 'Cloud'
       OR lower(entry_name) LIKE '%lagrange%'
       OR regexp_matches(lower(entry_name), '\\b[eklpqt]-type\\b')
       OR lower(entry_name) LIKE '%anomaly%')
""")

print("collecting green gas giants from all three catalogues...", flush=True)
con.execute("""
CREATE OR REPLACE TABLE staging.ph_ggg AS
SELECT id64 AS system_id64, 'canonn' AS source,
       TRY_CAST(reported_at AS TIMESTAMP) AS reported_at,
       english_name AS nsp_family
FROM canonn_codex_event
WHERE hud_category = 'Tourist'
  AND lower(english_name) LIKE '%green%' AND lower(english_name) LIKE '%giant%'
  AND id64 IS NOT NULL
UNION ALL
SELECT systemId64, 'edsm', TRY_CAST(reportedOn AS TIMESTAMP), 'Green Gas Giant'
FROM edsm_codex_entry WHERE name = 'Green Gas Giant' AND systemId64 IS NOT NULL
UNION ALL
SELECT id64, 'gec', CAST(NULL AS TIMESTAMP), 'Green Gas Giant'
FROM edastro_point_of_interest WHERE type = 'Green Gas Giants' AND id64 IS NOT NULL
""")

print("collapsing to (system, phenomenon)...", flush=True)
con.execute("""
CREATE OR REPLACE TABLE staging.ph_sys AS
WITH all_obs AS (
    SELECT system_id64, 'NSP' AS phenomenon, source, reported_at, nsp_family AS kind
    FROM staging.ph_obs
    UNION ALL
    SELECT system_id64, 'GGG', source, reported_at, nsp_family
    FROM staging.ph_ggg
)
SELECT system_id64, phenomenon,
       count(*)::INTEGER                                   AS observations,
       min(reported_at)                                    AS first_reported,
       max(reported_at)                                    AS last_reported,
       bool_or(source = 'canonn')                          AS from_canonn,
       bool_or(source = 'edsm')                            AS from_edsm,
       bool_or(source = 'gec')                             AS from_gec,
       coalesce(string_agg(DISTINCT nullif(kind, 'Green Gas Giant'), '+'
                           ORDER BY nullif(kind, 'Green Gas Giant')),
                CASE WHEN phenomenon = 'GGG' THEN 'Green Gas Giant' END) AS kinds
FROM all_obs
GROUP BY 1, 2
""")

con.execute("""
CREATE OR REPLACE TABLE staging.ph_ready AS
SELECT g.system_id, p.phenomenon, p.kinds, p.observations,
       p.first_reported, p.last_reported,
       p.from_canonn, p.from_edsm, p.from_gec
FROM staging.ph_sys p
JOIN system_known g ON g.id64 = p.system_id64
""")
for ph, n, res in con.execute("""
    SELECT p.phenomenon, count(*),
           count(*) FILTER (WHERE EXISTS (SELECT 1 FROM system_known g
                                          WHERE g.id64 = p.system_id64))
    FROM staging.ph_sys p GROUP BY 1 ORDER BY 1""").fetchall():
    print(f"  {ph}: {n:,} systems, {res:,} resolved to system_known "
          f"({n - res:,} unresolved, left out)")

before = table_count(con, TABLE)
con.execute(f"""
INSERT INTO {TABLE}
SELECT coalesce((SELECT max(system_phenomenon_id) FROM {TABLE}), 0)
         + row_number() OVER (ORDER BY r.system_id, r.phenomenon),
       r.system_id, r.phenomenon, r.kinds, r.observations,
       r.first_reported, r.last_reported, r.from_canonn, r.from_edsm, r.from_gec
FROM staging.ph_ready r
WHERE NOT EXISTS (SELECT 1 FROM {TABLE} t
                  WHERE t.system_id = r.system_id AND t.phenomenon = r.phenomenon)
""")
mid = table_count(con, TABLE)

CHANGED = """(t.kinds          IS DISTINCT FROM r.kinds
           OR t.observations   IS DISTINCT FROM r.observations
           OR t.first_reported IS DISTINCT FROM r.first_reported
           OR t.last_reported  IS DISTINCT FROM r.last_reported
           OR t.from_canonn    IS DISTINCT FROM r.from_canonn
           OR t.from_edsm      IS DISTINCT FROM r.from_edsm
           OR t.from_gec       IS DISTINCT FROM r.from_gec)"""
upd = count_then_update(
    con,
    f"""SELECT count(*) FROM {TABLE} t JOIN staging.ph_ready r
          ON r.system_id = t.system_id AND r.phenomenon = t.phenomenon
        WHERE {CHANGED}""",
    f"""UPDATE {TABLE} t SET
          kinds = r.kinds, observations = r.observations,
          first_reported = r.first_reported, last_reported = r.last_reported,
          from_canonn = r.from_canonn, from_edsm = r.from_edsm, from_gec = r.from_gec
        FROM staging.ph_ready r
        WHERE r.system_id = t.system_id AND r.phenomenon = t.phenomenon
          AND {CHANGED}""")

after = table_count(con, TABLE)
orphan = con.execute(f"""SELECT count(*) FROM {TABLE} t
    WHERE NOT EXISTS (SELECT 1 FROM staging.ph_ready r
                      WHERE r.system_id = t.system_id
                        AND r.phenomenon = t.phenomenon)""").fetchone()[0]
report_merge(TABLE, before, after, mid - before, upd, [])
print(f"  rows no longer produced by the sources: {orphan:,} "
      f"(LEFT IN PLACE -- this table records, it does not predict)")

print("\nby phenomenon:")
print(con.execute(f"""SELECT phenomenon, count(*) AS systems, sum(observations) AS obs,
        count(*) FILTER (WHERE from_canonn) AS canonn,
        count(*) FILTER (WHERE from_edsm)   AS edsm,
        count(*) FILTER (WHERE from_gec)    AS gec
    FROM {TABLE} GROUP BY 1 ORDER BY 1""").fetchdf().to_string(index=False))

apply_comment_file(con, comment_file(TABLE))
con.close()
print("\nDONE")

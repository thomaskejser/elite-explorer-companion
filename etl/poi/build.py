import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import INPUT, ROOT, connect, table_count

OUT = INPUT / "poi.parquet"
if OUT.exists():
    sys.exit(f"{OUT} already exists -- it is authoritative and hand-edited.\n"
             f"This seeder has no --force. Delete the file first, knowingly.")

con = connect(memory_limit="6GB", read_only=True)

# DUPLICATED, not shared through common/: etl/system_phenomenon/build.py carries the same
# classifier text. Change one and change the other, or phenomena reclassify silently.
FAMILY = """
CASE
  WHEN regexp_matches(lower(nm), 'bell|bulb|bullet|capsule|globe|gourd|parasol|reel|squid|torus|umbrella')
       AND lower(nm) LIKE '%mollusc%'                        THEN 'mollusc'
  WHEN lower(nm) LIKE '%tree%' OR lower(nm) LIKE '%void heart%' THEN 'plant'
  WHEN lower(nm) LIKE '%pod%'                                 THEN 'seed_pod'
  WHEN regexp_matches(lower(nm), 'crystal|calcite plate|mineral sphere')
                                                              THEN 'mineral_formation'
  WHEN lower(nm) LIKE '%lagrange%'                            THEN 'lagrange_cloud'
  WHEN regexp_matches(lower(nm), '\b[eklpqt][0-9]*-type\b')
       OR lower(nm) LIKE '%anomaly%'                          THEN 'anomaly'
  ELSE NULL
END"""

print("enumerating the POI universe from all three sources...", flush=True)
con.execute(f"""
CREATE OR REPLACE TEMP TABLE seed AS
WITH raw AS (
    SELECT english_name AS nm,
           CASE hud_category WHEN 'Cloud'    THEN 'nsp'
                             WHEN 'Anomaly'  THEN 'anomaly'
                             WHEN 'Guardian' THEN 'guardian'
                             WHEN 'Thargoid' THEN 'thargoid'
                             WHEN 'Tourist'  THEN 'ggg' END AS poi_class,
           hud_category IN ('Guardian', 'Thargoid')          AS needs_landing,
           'canonn' AS src
    FROM canonn_codex_event
    WHERE hud_category IN ('Cloud', 'Anomaly', 'Guardian', 'Thargoid')
       OR (hud_category = 'Tourist'
           AND lower(english_name) LIKE '%green%'
           AND lower(english_name) LIKE '%giant%')
    UNION ALL
    SELECT name, 'ggg', false, 'edsm'
    FROM edsm_codex_entry WHERE name = 'Green Gas Giant'
    UNION ALL
    SELECT type, CASE WHEN type = 'Green Gas Giants' THEN 'ggg' ELSE 'gec' END,
           false, 'gec'
    FROM edastro_point_of_interest WHERE type IS NOT NULL
)
SELECT nm AS poi,
       any_value(poi_class)                    AS poi_class,
       {FAMILY}                                AS poi_family,
       bool_or(needs_landing)                  AS needs_landing,
       string_agg(DISTINCT src, '+' ORDER BY src) AS sources
FROM raw
WHERE nm IS NOT NULL AND trim(nm) <> ''
GROUP BY nm
""")

n = table_count(con, 'seed')
print(f"  {n:,} distinct POI kinds")
print(con.execute("""SELECT poi_class, count(*) kinds,
        count(*) FILTER (WHERE needs_landing) needs_landing
    FROM seed GROUP BY 1 ORDER BY 2 DESC""").fetchdf().to_string(index=False))

con.execute(f"""
COPY (
  SELECT CAST(row_number() OVER (ORDER BY poi_class, poi) AS INTEGER) AS poi_id,
         poi, poi_class, poi_family, needs_landing, sources,
         CAST(NULL AS INTEGER) AS systems,
         CAST(NULL AS INTEGER) AS bodies
  FROM seed
) TO '{OUT.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)
""")
con.close()
print(f"\nwrote {OUT}")
print("  HAND-CURATE IT before loading: the GEC `type` values overlap by case and\n"
      "  plural ('nebula' vs 'Nebulae'), and only you can say which are worth a trip.")
print("\nDONE_BUILD_POI")

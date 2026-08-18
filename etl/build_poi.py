"""Seed `input/poi.parquet` -- the distinct POINTS OF INTEREST we track.

LOADED table (ETL.md 2): this script is a ONE-TIME SEEDER. It writes ONLY the parquet,
never the table, it refuses to run once the file exists, and there is no --force. The
parquet is authoritative and hand-editable -- POI curation (merging EDAstro's `nebula`
and `Nebulae`, deciding what is worth flying to) is a JUDGEMENT CALL, so corrections
are made by hand and regenerating would discard them. `etl/load_poi.py` is the only
thing allowed to write the table.

NOT scripts/build_poi.py. That legacy script exports app/poi.parquet, a flight target
list; it predates etl/ and should be retired once the app reads this table instead.

WHAT COUNTS AS A POI HERE. A thing you fly to LOOK at, which the game credits to you
personally however many commanders logged it first. That is the whole reason the `poi`
dimension is separate from prediction: a black hole somebody already scanned is worth
nothing, a Lagrange cloud is worth the same to everyone.

  poi_class   source                        note
  nsp         canonn hud_category='Cloud'   133 kinds. Far broader than "cloud":
                                            crystals, peduncle trees, bulb molluscs and
                                            quadripartite pods all announce as "Notable
                                            stellar phenomena" in the nav panel.
  anomaly     canonn hud_category='Anomaly' 53 kinds, the [EKLPQT]nn-Type series.
  ggg         3 catalogues, unioned on id64 Green gas giants. A COLOUR BUG, not a body
                                            type; DEAD_ENDS.md records that they cannot
                                            be predicted, so the catalogue is the only
                                            supply.
  guardian    canonn hud_category='Guardian'  6 kinds, almost always body-attributed.
  thargoid    canonn hud_category='Thargoid' 21 kinds, almost always body-attributed.
  gec         edastro_point_of_interest     Curated GEC feed: nebulae, stellar remnants,
                                            historical sites. Messiest source -- its
                                            `type` values overlap by case and plural,
                                            which is exactly what hand-curation is for.

TWO CATEGORIES ARE DELIBERATELY EXCLUDED, and the counts are why:

  Biology  924,883 systems. Organic sampling, not a point of interest -- it would swamp
           every other class by an order of magnitude and turn `id_poi` into a biology
           flag.
  Geology   97,788 systems. Needs a LANDING, not a look. A different kind of trip, and
           the legacy build_poi.py excluded it for the same reason.

`needs_landing` is carried per row rather than per class because Guardian and Thargoid
sites are surface sites: they are real POIs, but they cost a landing, and a router that
cannot land must be able to filter them out.

Usage:  python etl/build_poi.py
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common.db import ROOT, INPUT, connect

OUT = INPUT / "poi.parquet"
if OUT.exists():
    sys.exit(f"{OUT} already exists -- it is authoritative and hand-edited.\n"
             f"This seeder has no --force. Delete the file first, knowingly.")

con = connect(memory_limit="6GB", read_only=True)

# The family classifier is IDENTICAL to build_system_phenomenon.py's, which is itself
# ported from norm.codex_observation. A divergence between the three would silently
# reclassify phenomena, so if you change one, change all three.
FAMILY = """
CASE
  WHEN regexp_matches(lower(nm), 'bell|bulb|bullet|capsule|globe|gourd|parasol|reel|squid|torus|umbrella')
       AND lower(nm) LIKE '%mollusc%'                        THEN 'mollusc'
  WHEN lower(nm) LIKE '%tree%' OR lower(nm) LIKE '%void heart%' THEN 'plant'
  WHEN lower(nm) LIKE '%pod%'                                 THEN 'seed_pod'
  WHEN regexp_matches(lower(nm), 'crystal|calcite plate|mineral sphere')
                                                              THEN 'mineral_formation'
  WHEN lower(nm) LIKE '%lagrange%'                            THEN 'lagrange_cloud'
  WHEN regexp_matches(lower(nm), '\\b[eklpqt][0-9]*-type\\b')
       OR lower(nm) LIKE '%anomaly%'                          THEN 'anomaly'
  ELSE NULL
END"""

print("enumerating the POI universe from all three sources...", flush=True)
con.execute(f"""
CREATE OR REPLACE TEMP TABLE seed AS
WITH raw AS (
    -- canonn: the only source carrying a hud_category, so the only reliable classifier
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
       -- Tourist is mostly not a POI; the green giants are the part we want.
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

n = con.execute("SELECT count(*) FROM seed").fetchone()[0]
print(f"  {n:,} distinct POI kinds")
print(con.execute("""SELECT poi_class, count(*) kinds,
        count(*) FILTER (WHERE needs_landing) needs_landing
    FROM seed GROUP BY 1 ORDER BY 2 DESC""").fetchdf().to_string(index=False))

# systems/bodies are DERIVED counts recomputed by the loader (ETL.md 2: don't put
# derived statistics in input/). Seeded NULL so the parquet never looks authoritative
# about them.
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

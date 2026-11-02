CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.ph_obs;

CREATE TABLE transform.ph_obs (
    system_id64 BIGINT    NOT NULL,
    phenomenon  VARCHAR   NOT NULL CHECK (phenomenon IN ('NSP', 'GGG')),
    source      VARCHAR   NOT NULL CHECK (source IN ('canonn', 'edsm', 'gec')),
    reported_at TIMESTAMP,
    kind        VARCHAR
);

INSERT INTO transform.ph_obs (system_id64, phenomenon, source, reported_at, kind)
WITH codex AS (
    SELECT id64 AS system_id64, hud_category, english_name AS entry_name,
           TRY_CAST(reported_at AS TIMESTAMP) AS reported_at, 'canonn' AS source
    FROM staging.canonn_codex_event
    UNION ALL
    SELECT systemId64, CAST(NULL AS VARCHAR), name,
           TRY_CAST(reportedOn AS TIMESTAMP), 'edsm'
    FROM staging.edsm_codex_entry
)
SELECT system_id64, 'NSP', source, reported_at,
       CASE
         WHEN regexp_matches(lower(entry_name), 'bell|bulb|bullet|capsule|globe|gourd|parasol|reel|squid|torus|umbrella')
              AND lower(entry_name) LIKE '%mollusc%'                    THEN 'mollusc'
         WHEN lower(entry_name) LIKE '%tree%'
              OR lower(entry_name) LIKE '%void heart%'                  THEN 'plant'
         WHEN lower(entry_name) LIKE '%pod%'                            THEN 'seed_pod'
         WHEN regexp_matches(lower(entry_name), 'crystal|calcite plate|mineral sphere')
                                                                        THEN 'mineral_formation'
         WHEN lower(entry_name) LIKE '%lagrange%'                       THEN 'lagrange_cloud'
         WHEN regexp_matches(lower(entry_name), '\b[eklpqt]-type\b')
              OR lower(entry_name) LIKE '%anomaly%'                     THEN 'anomaly'
         ELSE NULL
       END
FROM codex
WHERE system_id64 IS NOT NULL
  AND (hud_category = 'Cloud'
       OR lower(entry_name) LIKE '%lagrange%'
       OR regexp_matches(lower(entry_name), '\b[eklpqt]-type\b')
       OR lower(entry_name) LIKE '%anomaly%')
UNION ALL
SELECT id64, 'GGG', 'canonn', TRY_CAST(reported_at AS TIMESTAMP), english_name
FROM staging.canonn_codex_event
WHERE hud_category = 'Tourist'
  AND lower(english_name) LIKE '%green%' AND lower(english_name) LIKE '%giant%'
  AND id64 IS NOT NULL
UNION ALL
SELECT systemId64, 'GGG', 'edsm', TRY_CAST(reportedOn AS TIMESTAMP), 'Green Gas Giant'
FROM staging.edsm_codex_entry
WHERE name = 'Green Gas Giant' AND systemId64 IS NOT NULL
UNION ALL
SELECT id64, 'GGG', 'gec', CAST(NULL AS TIMESTAMP), 'Green Gas Giant'
FROM staging.edastro_point_of_interest
WHERE type = 'Green Gas Giants' AND id64 IS NOT NULL;

COMMENT ON TABLE transform.ph_obs IS
'TRANSFORM: every codex or GEC observation that counts as a notable phenomenon, one row per REPORT, labelled NSP (notable stellar phenomenon) or GGG (green gas giant). Built from staging.canonn_codex_event, staging.edsm_codex_entry and staging.edastro_point_of_interest; rebuilt on every load of main.system_phenomenon -- derived, never edited, safe to drop.

*** ONE ROW PER REPORT, NOT PER SYSTEM. *** Busy systems are reported many times, so a row count measures commander traffic rather than the galaxy. transform.system_phenomenon reduces it to one row per (system, phenomenon).

The NSP family classifier here is DUPLICATED in input/poi.parquet''s poi_family rather than shared, and the two anomaly patterns already differ -- a phenomenon can therefore read as a different family depending on which table you ask.';

COMMENT ON COLUMN transform.ph_obs.system_id64 IS
'The game''s id64 as the feed reports it, which is also main.system_known.system_id. NOT yet resolved: a value with no system_known row is dropped by transform.system_phenomenon, never here.';

COMMENT ON COLUMN transform.ph_obs.phenomenon IS
'NSP for a Canonn Cloud / lagrange / [eklpqt]-type / anomaly entry, GGG for a green gas giant. The grain of main.system_phenomenon.';

COMMENT ON COLUMN transform.ph_obs.source IS
'Which feed made the report: canonn, edsm or gec (the EDAstro Galactic Exploration Catalog). One report is one row, so the same sighting reported to two feeds is two rows.';

COMMENT ON COLUMN transform.ph_obs.reported_at IS
'When the commander reported it, as the feed records it. NULL for every GEC row -- the catalogue carries no time -- so it is NOT a discovery date and must not be read as one.';

COMMENT ON COLUMN transform.ph_obs.kind IS
'NSP: the family parsed from the entry name (mollusc, plant, seed_pod, mineral_formation, lagrange_cloud, anomaly), NULL when no pattern matches. GGG: the Canonn entry name, or the literal ''Green Gas Giant'' for EDSM and GEC. A heuristic label from names, not a feed classification.';

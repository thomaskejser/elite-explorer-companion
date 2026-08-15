-- Elite Mapping: normalized modelling layer
-- Built 2026-07-12 from raw provider snapshots (see ingest_manifest).
-- Design refs: 03-prediction-engine-design.md, 04-dataset-overlap-and-lineage.md
--
-- Principles enforced here:
--   * Join by stable id64, never by name.
--   * Preserve source lineage; do not silently overwrite conflicting facts.
--   * galaxy_version is UNKNOWN for EDSM/EDAstro/Canonn dumps (Live vs Legacy is
--     not distinguished in these feeds) -- recorded honestly, never guessed.
--   * "Not reported" is UNKNOWN, not a negative label.

CREATE SCHEMA IF NOT EXISTS norm;

-- ---------------------------------------------------------------------------
-- system: full known-system spine (EDSM systemsWithCoordinates = 97M).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW norm.system AS
SELECT
    id64                       AS system_id64,
    name                       AS system_name,
    coords.x                   AS x,
    coords.y                   AS y,
    coords.z                   AS z,
    sqrt(coords.x*coords.x + coords.y*coords.y + coords.z*coords.z) AS dist_from_sol_ly,
    date                       AS observed_at,
    'edsm'                     AS source,
    'unknown'                  AS galaxy_version
FROM edsm_star_system
WHERE id64 IS NOT NULL;

-- ---------------------------------------------------------------------------
-- body: full-galaxy body facts, built on the Spansh galaxy dump (~570M bodies,
-- ~195M systems). This replaces the earlier EDSM 7-day slice as the body spine.
-- Exposes the DSS signal-derived geology/biology counts, which are direct
-- labels for the exobiology/geology models. EDSM's 7-day bodies remain
-- available as `edsm_celestial_body` for freshness overlay/reconciliation.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW norm.body AS
SELECT
    system_id64,
    body_id,
    body_id64,
    name                       AS body_name,
    type                       AS body_type,
    sub_type                   AS body_subtype,
    is_landable,
    dist_to_arrival_ls,
    surface_temp_k,
    gravity, earth_masses, radius, surface_pressure,
    volcanism_type,
    atmosphere_type,
    terraforming_state,
    solar_masses, solar_radius, spectral_class, luminosity,
    ring_count,
    signal_geology, signal_biology,
    (coalesce(signal_geology, 0) > 0)   AS has_geology,
    (coalesce(signal_biology, 0) > 0)   AS has_biology,
    genuses,
    update_time                AS observed_at,
    'spansh'                   AS source,
    'unknown'                  AS galaxy_version
FROM spansh_body;

-- ---------------------------------------------------------------------------
-- codex_observation: unified codex reports (EDSM + Canonn), with an NSP flag
-- and a phenomenon-family classifier derived from doc 02's taxonomy.
-- These are OBSERVATIONS (someone reported it), not proof of presence.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW norm.codex_observation AS
WITH canonn AS (
    SELECT
        id64                                        AS system_id64,
        system                                      AS system_name,
        TRY_CAST(x AS DOUBLE)                        AS x,
        TRY_CAST(y AS DOUBLE)                        AS y,
        TRY_CAST(z AS DOUBLE)                        AS z,
        NULLIF(body, '')                            AS body_name,
        TRY_CAST(latitude  AS DOUBLE)               AS latitude,
        TRY_CAST(longitude AS DOUBLE)               AS longitude,
        hud_category                                AS hud_category,
        english_name                                AS entry_name,
        reported_at                                 AS reported_at,
        'canonn'                                    AS source
    FROM canonn_codex_event
),
edsm AS (
    SELECT
        systemId64                                  AS system_id64,
        systemName                                  AS system_name,
        CAST(NULL AS DOUBLE) AS x, CAST(NULL AS DOUBLE) AS y, CAST(NULL AS DOUBLE) AS z,
        CAST(NULL AS VARCHAR)                        AS body_name,
        CAST(NULL AS DOUBLE) AS latitude, CAST(NULL AS DOUBLE) AS longitude,
        CAST(NULL AS VARCHAR)                        AS hud_category,
        name                                         AS entry_name,
        reportedOn                                   AS reported_at,
        'edsm'                                       AS source
    FROM edsm_codex_entry
),
u AS (SELECT * FROM canonn UNION ALL SELECT * FROM edsm)
SELECT
    *,
    -- NSP = Notable Stellar Phenomena. Canonn 'Cloud' hud_category is the
    -- reliable flag; EDSM anomaly types (l/k/e/p/q/t) are the anomaly subset.
    (hud_category = 'Cloud'
        OR lower(entry_name) LIKE '%lagrange%'
        OR regexp_matches(lower(entry_name), '\\b[eklpqt]-type\\b')
        OR lower(entry_name) LIKE '%anomaly%')      AS is_nsp,
    CASE
        WHEN regexp_matches(lower(entry_name), 'bell|bulb|bullet|capsule|globe|gourd|parasol|reel|squid|torus|umbrella') AND lower(entry_name) LIKE '%mollusc%' THEN 'mollusc'
        WHEN lower(entry_name) LIKE '%tree%' OR lower(entry_name) LIKE '%void heart%' THEN 'plant'
        WHEN lower(entry_name) LIKE '%pod%' THEN 'seed_pod'
        WHEN regexp_matches(lower(entry_name), 'crystal|calcite plate|mineral sphere') THEN 'mineral_formation'
        WHEN lower(entry_name) LIKE '%lagrange%' THEN 'lagrange_cloud'
        WHEN regexp_matches(lower(entry_name), '\\b[eklpqt]-type\\b') OR lower(entry_name) LIKE '%anomaly%' THEN 'anomaly'
        ELSE NULL
    END                                              AS nsp_family,
    'unknown'                                        AS galaxy_version
FROM u;

-- ---------------------------------------------------------------------------
-- poi: curated points of interest (EDAstro Galactic Exploration Catalog).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW norm.poi AS
SELECT
    id64                       AS system_id64,
    name                       AS poi_name,
    type                       AS poi_type,
    region,
    CASE WHEN len(coordinates) = 3 THEN coordinates[1] END AS x,
    CASE WHEN len(coordinates) = 3 THEN coordinates[2] END AS y,
    CASE WHEN len(coordinates) = 3 THEN coordinates[3] END AS z,
    solDistance                AS dist_from_sol_ly,
    rare, rating, votes,
    'edastro_gec'              AS source,
    'unknown'                  AS galaxy_version
FROM edastro_point_of_interest;

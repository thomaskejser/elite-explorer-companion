CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.station;

CREATE TABLE transform.station AS
WITH flagged AS (
    SELECT s.id AS market_id, s.system_id64 AS system_id, s.system_name AS system, s.name AS station,
           s.type AS station_type, coalesce(s.type = 'Drake-Class Carrier', false) AS is_carrier,
           s.distance_to_arrival AS distance_to_arrival_ls, s.large_pads,
           coalesce(list_contains(s.services, 'Universal Cartographics'), false) AS has_universal_cartographics,
           coalesce(list_contains(s.services, 'Vista Genomics'), false) AS has_vista_genomics,
           coalesce(list_contains(s.services, 'Repair'), false) AS has_repair,
           coalesce(list_contains(s.services, 'Restock'), false) AS has_restock,
           coalesce(list_contains(s.services, 'Refuel'), false) AS has_refuel,
           s.update_time AS last_reported, s.x, s.y, s.z
    FROM staging.spansh_galaxy_station s
    WHERE s.id IS NOT NULL AND s.system_id64 IS NOT NULL AND s.name IS NOT NULL AND s.x IS NOT NULL
)
SELECT * FROM flagged
WHERE has_universal_cartographics OR has_vista_genomics
   OR (has_repair AND has_restock AND coalesce(large_pads, 0) > 0)
QUALIFY row_number() OVER (PARTITION BY market_id ORDER BY last_reported DESC NULLS LAST) = 1;

COMMENT ON TABLE transform.station IS
'TRANSFORM: staging.spansh_galaxy_station reduced to the stations main.station holds -- Universal Cartographics, Vista Genomics, or repair and rearm on a large pad -- one row per MarketID, shaped exactly as main.station merges it. Rebuilt on every load, safe to drop.';

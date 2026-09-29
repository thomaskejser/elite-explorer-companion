CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.station_service;

CREATE TABLE transform.station_service (
    market_id                   BIGINT  NOT NULL PRIMARY KEY,
    system_id                   BIGINT  NOT NULL,
    system                      VARCHAR NOT NULL,
    station                     VARCHAR NOT NULL CHECK (trim(station) <> ''),
    station_type                VARCHAR,
    distance_to_arrival_ls      DOUBLE,
    is_planetary                BOOLEAN NOT NULL,
    has_large_pad               BOOLEAN,
    material_trader             VARCHAR CHECK (material_trader IN ('Encoded', 'Manufactured', 'Raw')),
    technology_broker           VARCHAR CHECK (technology_broker IN ('Human', 'Guardian')),
    has_universal_cartographics BOOLEAN NOT NULL,
    last_reported               TIMESTAMP,
    x                           DOUBLE,
    y                           DOUBLE,
    z                           DOUBLE,
    CHECK (material_trader IS NOT NULL OR technology_broker IS NOT NULL)
);

INSERT INTO transform.station_service
SELECT s.market_id, s.system_id64,
       CASE WHEN k.sector_id = 0 OR sc.sector IS NULL THEN k.system_in_sector
            ELSE sc.sector || ' ' || k.system_in_sector END,
       trim(s.name), s.type, s.distance_to_arrival,
       coalesce(s.is_planetary, false), s.has_large_pad,
       s.material_trader, s.technology_broker,
       coalesce(list_contains(s.services, 'Universal Cartographics'), false),
       s.updated_at, k.x, k.y, k.z
FROM staging.spansh_station_service s
JOIN main.system_known k ON k.system_id = s.system_id64
LEFT JOIN main.sector sc ON sc.sector_id = k.sector_id
WHERE s.market_id IS NOT NULL;

COMMENT ON TABLE transform.station_service IS
'TRANSFORM: staging.spansh_station_service shaped exactly as main.station_service merges it, with each station''s system coordinates taken from main.system_known. Rebuilt on every load -- derived, never edited, safe to drop.

Its constraints are the input validation: one row per market_id, a non-blank name, only the service values the feed is known to use, and at least one of the two services on every row. A station whose system_id64 is not in system_known is left out here and counted by the loader.';

COMMENT ON COLUMN transform.station_service.market_id IS 'The game''s market id, the natural key main.station_service merges on. PRIMARY KEY here so a duplicate fails before the merge.';
COMMENT ON COLUMN transform.station_service.system_id IS 'The staged system_id64, kept only where it is a system in main.system_known.';
COMMENT ON COLUMN transform.station_service.system IS 'The full system name, composed from main.system_known and main.sector; sector_id 0 stands alone.';
COMMENT ON COLUMN transform.station_service.station IS 'Station name, trimmed. Not unique; never a key.';
COMMENT ON COLUMN transform.station_service.station_type IS 'Spansh''s station class, as staged.';
COMMENT ON COLUMN transform.station_service.distance_to_arrival_ls IS 'Distance from the arrival star in light-seconds, as staged.';
COMMENT ON COLUMN transform.station_service.is_planetary IS 'TRUE for a surface port; a missing flag is FALSE.';
COMMENT ON COLUMN transform.station_service.has_large_pad IS 'TRUE when the station has a large pad; NULL where the feed reports none.';
COMMENT ON COLUMN transform.station_service.material_trader IS '''Encoded'', ''Manufactured'', ''Raw'' or NULL, checked.';
COMMENT ON COLUMN transform.station_service.technology_broker IS '''Human'', ''Guardian'' or NULL, checked.';
COMMENT ON COLUMN transform.station_service.has_universal_cartographics IS 'TRUE when the staged service list contains Universal Cartographics.';
COMMENT ON COLUMN transform.station_service.last_reported IS 'The staged updated_at: the last EDDN report of the station.';
COMMENT ON COLUMN transform.station_service.x IS 'main.system_known.x for the station''s system.';
COMMENT ON COLUMN transform.station_service.y IS 'main.system_known.y for the station''s system.';
COMMENT ON COLUMN transform.station_service.z IS 'main.system_known.z for the station''s system.';

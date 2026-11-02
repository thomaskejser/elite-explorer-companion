CREATE TABLE IF NOT EXISTS station (
    market_id                   BIGINT  NOT NULL PRIMARY KEY,
    system_id                   BIGINT  NOT NULL,
    system                      VARCHAR NOT NULL,
    station                     VARCHAR NOT NULL,
    station_type                VARCHAR,
    is_carrier                  BOOLEAN NOT NULL,
    distance_to_arrival_ls      DOUBLE,
    large_pads                  INTEGER,
    has_universal_cartographics BOOLEAN NOT NULL,
    has_vista_genomics          BOOLEAN NOT NULL,
    has_repair                  BOOLEAN NOT NULL,
    has_restock                 BOOLEAN NOT NULL,
    has_refuel                  BOOLEAN NOT NULL,
    last_reported               TIMESTAMPTZ,
    is_listed                   BOOLEAN NOT NULL,
    x DOUBLE, y DOUBLE, z DOUBLE
);

COMMENT ON TABLE station IS
'Every station an explorer comes back to: one row per station, settlement, megaship or fleet carrier offering Universal Cartographics, Vista Genomics, or repair and rearm on a large pad. From Spansh''s galaxy_stations dump (staging.spansh_galaxy_station) by etl/station/refresh.py. Read by the overlay''s Trade tab, through the app-state mirror.

NEVER DELETES: a station no longer in the dump, or no longer offering any of the three, keeps its row with is_listed FALSE, and every read must filter on is_listed.

*** A FLEET CARRIER MOVES. *** Its row is where it was last reported (last_reported), which can be years old; read a carrier''s position only with a recent last_reported. Material traders and technology brokers are main.station_service, not here.';

COMMENT ON COLUMN station.market_id IS 'The game''s MarketID, the natural key.';
COMMENT ON COLUMN station.system_id IS 'The game''s id64, main.system_known.system_id.';
COMMENT ON COLUMN station.system IS 'System name as Spansh spells it.';
COMMENT ON COLUMN station.station IS 'Station name; a fleet carrier''s callsign.';
COMMENT ON COLUMN station.station_type IS 'Spansh''s station type.';
COMMENT ON COLUMN station.is_carrier IS 'TRUE for a Drake-Class fleet carrier, whose position goes stale.';
COMMENT ON COLUMN station.distance_to_arrival_ls IS 'Light-seconds from the arrival star.';
COMMENT ON COLUMN station.large_pads IS 'Large landing pads, NULL when Spansh gives no pad counts.';
COMMENT ON COLUMN station.has_universal_cartographics IS 'Sells exploration data.';
COMMENT ON COLUMN station.has_vista_genomics IS 'Buys exobiology samples.';
COMMENT ON COLUMN station.has_repair IS 'Offers repair.';
COMMENT ON COLUMN station.has_restock IS 'Offers restock (rearm).';
COMMENT ON COLUMN station.has_refuel IS 'Offers refuel.';
COMMENT ON COLUMN station.last_reported IS 'When Spansh last received the station''s data.';
COMMENT ON COLUMN station.is_listed IS 'FALSE once the latest dump no longer has the station offering any of the three. Filter on it.';
COMMENT ON COLUMN station.x IS 'System x in ly at last_reported.';
COMMENT ON COLUMN station.y IS 'System y in ly at last_reported.';
COMMENT ON COLUMN station.z IS 'System z in ly at last_reported.';

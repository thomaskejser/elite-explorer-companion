CREATE TABLE IF NOT EXISTS station_service (
    market_id                   BIGINT  NOT NULL PRIMARY KEY,
    system_id                   BIGINT  NOT NULL,
    system                      VARCHAR NOT NULL,
    station                     VARCHAR NOT NULL,
    station_type                VARCHAR,
    distance_to_arrival_ls      DOUBLE,
    is_planetary                BOOLEAN NOT NULL,
    has_large_pad               BOOLEAN,
    material_trader             VARCHAR,
    technology_broker           VARCHAR,
    has_universal_cartographics BOOLEAN NOT NULL,
    last_reported               TIMESTAMP,
    is_listed                   BOOLEAN NOT NULL,
    x                           DOUBLE,
    y                           DOUBLE,
    z                           DOUBLE
);

COMMENT ON TABLE station_service IS
'Every station carrying a MATERIAL TRADER or a TECHNOLOGY BROKER, one row per station. From Spansh''s station search API, filtered to those two services (staging.spansh_station_service), merged by etl/station_service/refresh.py. Mirrored into elite_mapping_v2_current.duckdb for the overlay.

*** A SERVICE CENSUS, NOT A STATION CENSUS. *** Only stations offering one of the two services are here; a station''s absence says nothing about it, and no count taken here is a count of stations, systems or the bubble.

*** ROWS ARE NEVER DELETED; is_listed SAYS WHETHER THE SERVICE IS STILL THERE. *** Each pull is the complete set of stations offering these services, so a station missing from the latest pull no longer offers either one as far as Spansh knows. Its row stays with is_listed = FALSE and comes back to TRUE if a later pull lists it again. Offer a commander only is_listed rows.

x, y and z are the SYSTEM''s coordinates, copied from system_known on every load so the overlay can rank stations by distance without the 200M-row table. They are not the station''s own position and carry no information system_known lacks.';

COMMENT ON COLUMN station_service.market_id IS
'The game''s market id for the station, and the natural key. Stable across renames; the merge matches on it.';

COMMENT ON COLUMN station_service.system_id IS
'The station''s system: the game''s id64, which IS system_known.system_id. Never resolve a station by system name -- full system names are not unique.';

COMMENT ON COLUMN station_service.system IS
'The station''s full system name, composed from system_known and sector on every load exactly as the rest of the model composes it (sector_id 0 stands alone). What the overlay pastes into the galaxy map. NOT unique -- full names repeat -- so never a key; system_id is.';

COMMENT ON COLUMN station_service.station IS
'Station name as Spansh spells it. NOT unique across the galaxy; for display, never for joining.';

COMMENT ON COLUMN station_service.station_type IS
'Station class as Spansh labels it ("Coriolis Starport", "Planetary Outpost", "Mega ship"). No fleet carrier offers either service, so none appears here.';

COMMENT ON COLUMN station_service.distance_to_arrival_ls IS
'Distance from the arrival star to the station, in light-seconds. The cost of reaching the service once the jump is made, and what decides between two stations offering the same one.';

COMMENT ON COLUMN station_service.is_planetary IS
'TRUE for a surface port, which costs a descent and a landing rather than a docking.';

COMMENT ON COLUMN station_service.has_large_pad IS
'TRUE when the station has a large landing pad, the go/no-go for a large ship. NULL where Spansh reports no pad information, which is unknown rather than no.';

COMMENT ON COLUMN station_service.material_trader IS
'Which materials this trader exchanges: ''Encoded'', ''Manufactured'' or ''Raw''. NULL means the station has no material trader, not that its type is unknown.';

COMMENT ON COLUMN station_service.technology_broker IS
'Which unlocks this broker offers: ''Human'' or ''Guardian''. NULL means the station has no technology broker. A station may carry both services, so both columns can be set.';

COMMENT ON COLUMN station_service.has_universal_cartographics IS
'TRUE when the station''s service list includes Universal Cartographics, the explorer''s other reason to dock. FALSE, never NULL, where the list lacks it.';

COMMENT ON COLUMN station_service.last_reported IS
'When EDDN last received a report about this station, per Spansh. The staleness signal: a service is only as current as the last commander who docked and reported it.';

COMMENT ON COLUMN station_service.is_listed IS
'TRUE when the most recent pull lists this station; FALSE when it has dropped out, meaning Spansh no longer reports either service there. Set by every load, which is the only thing that changes it.';

COMMENT ON COLUMN station_service.x IS
'Galactic x of the station''s SYSTEM in ly, copied from system_known.x on every load. Not the station''s own offset from the star.';

COMMENT ON COLUMN station_service.y IS
'Galactic y of the station''s system in ly, copied from system_known.y. See x.';

COMMENT ON COLUMN station_service.z IS
'Galactic z of the station''s system in ly, copied from system_known.z. See x.';

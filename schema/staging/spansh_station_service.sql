CREATE TABLE IF NOT EXISTS staging.spansh_station_service (
    market_id           BIGINT,
    id                  VARCHAR,
    name                VARCHAR,
    type                VARCHAR,
    system_id64         BIGINT,
    system_name         VARCHAR,
    system_x            DOUBLE,
    system_y            DOUBLE,
    system_z            DOUBLE,
    system_population   BIGINT,
    distance_to_arrival DOUBLE,
    is_planetary        BOOLEAN,
    body_id64           BIGINT,
    body_name           VARCHAR,
    body_type           VARCHAR,
    body_subtype        VARCHAR,
    latitude            DOUBLE,
    longitude           DOUBLE,
    has_large_pad       BOOLEAN,
    large_pads          BIGINT,
    medium_pads         BIGINT,
    small_pads          BIGINT,
    has_market          BOOLEAN,
    has_outfitting      BOOLEAN,
    has_shipyard        BOOLEAN,
    material_trader     VARCHAR,
    technology_broker   VARCHAR,
    services            VARCHAR[],
    primary_economy     VARCHAR,
    secondary_economy   VARCHAR,
    government          VARCHAR,
    allegiance          VARCHAR,
    updated_at          TIMESTAMP
);

COMMENT ON TABLE staging.spansh_station_service IS
'RAW SOURCE (not a work table -- never drop or rebuild): every station Spansh knows to carry a Material Trader or a Technology Broker, pulled from the POST https://spansh.co.uk/api/stations/search API by etl/station_service/stage.py. One row per STATION, ~4.4k rows; a station carrying both services appears once, with both material_trader and technology_broker set.

*** A SERVICE CENSUS, NOT A STATION CENSUS. *** Only stations matching one of the two filters are here. The absence of a station says nothing about that station, and a count taken here is never a count of stations, of systems, or of the bubble.

*** NOT A DUMP: A FILTERED QUERY, AND THE QUERY IS THE PROVENANCE. *** Spansh''s galaxy_stations.json.gz (4.15 GB) carries the same field for every station in the galaxy; this feed asks for the ~4.4k that answer the question and is seconds rather than a multi-GB parse. The cost is that there is no ETag, no Last-Modified and no file to validate against the server, so common.sources.download() cannot be used and every run re-pulls. The stager''s integrity check stands in for the validator: each filter''s pulled row count must equal the count the API reports for it, or nothing is written.

*** THE API SILENTLY IGNORES AN UNKNOWN FILTER NAME *** and returns the unfiltered galaxy capped at 10,000 results. Any count of exactly 10000 from that endpoint is the cap and means the filter did nothing -- it is not a measurement. The stager refuses a pull that reports it.

The API also returns each station''s full market, outfitting and shipyard inventories and its commodity and economy-share lists. NONE of that reaches raw/spansh_station_service.jsonl: keeping it costs 624 MB per pull against 7.9 MB without it, so the stager drops those blocks as it writes and the raw file is a TRIMMED response, not a byte-faithful one. It also drops `distance`, which is distance from whatever system the query named and measures the query, not the station. The faction, power and colonisation fields survive into the file but are not staged -- they change weekly and answer no question this model asks. Widen etl/station_service/stage.py''s DROP_FIELDS and COLUMNS if any of it is ever wanted.';

COMMENT ON COLUMN staging.spansh_station_service.market_id IS
'The game''s market id for the station, and the only stable key here. Unique in this table -- the stager deduplicates on it, because the two filter pulls overlap wherever a station carries both services.';

COMMENT ON COLUMN staging.spansh_station_service.id IS
'Spansh''s own station id, as a string. An internal handle of theirs, not a game identifier; never join on it. Use market_id.';

COMMENT ON COLUMN staging.spansh_station_service.name IS
'Station name as Spansh spells it. NOT UNIQUE across the galaxy and not a key; a fleet carrier''s name is commander-chosen and changes.';

COMMENT ON COLUMN staging.spansh_station_service.type IS
'Station class ("Orbis Starport", "Coriolis Starport", "Planetary Outpost", "Drake-Class Carrier"). A Drake-Class Carrier is a FLEET CARRIER and can jump away: its position here is a snapshot, exactly as in staging.edastro_fleet_carrier.';

COMMENT ON COLUMN staging.spansh_station_service.system_id64 IS
'The game''s id64 for the station''s system, and THE ONLY column the model joins on -- it IS system_known.system_id. Never match these rows by system_name: 1,477 full names belong to more than one system.';

COMMENT ON COLUMN staging.spansh_station_service.system_name IS
'System name as Spansh spells it. For display and for cross-checking the id64 resolution, never for joining.';

COMMENT ON COLUMN staging.spansh_station_service.system_x IS
'Galactic x of the SYSTEM in ly, as Spansh holds it. Cross-check only: any model position must come from system_known so that one system cannot sit at two sets of coordinates.';

COMMENT ON COLUMN staging.spansh_station_service.system_y IS 'Galactic y of the system in ly. See system_x: cross-check only.';

COMMENT ON COLUMN staging.spansh_station_service.system_z IS 'Galactic z of the system in ly. See system_x: cross-check only.';

COMMENT ON COLUMN staging.spansh_station_service.system_population IS
'Population of the system. Zero for a system whose only station is a fleet carrier, which is the usual case for a trader or broker out in the black.';

COMMENT ON COLUMN staging.spansh_station_service.distance_to_arrival IS
'Distance from the arrival star to the station in ls. The whole cost of using it once the jump is made, and the field that decides between two stations offering the same service.';

COMMENT ON COLUMN staging.spansh_station_service.is_planetary IS
'TRUE for a surface port, which costs a descent and a landing rather than a docking.';

COMMENT ON COLUMN staging.spansh_station_service.body_id64 IS
'id64 of the body the station orbits or sits on. NULL on all but a handful of rows -- the API omits the body block for most stations -- so this is not a usable join to main.body.';

COMMENT ON COLUMN staging.spansh_station_service.body_name IS
'Name of the body the station belongs to. NULL on nearly every row; see body_id64.';

COMMENT ON COLUMN staging.spansh_station_service.body_type IS
'Planet or Star, for the few rows carrying a body block. NULL on nearly every row.';

COMMENT ON COLUMN staging.spansh_station_service.body_subtype IS
'Body class ("Metal-rich body") for the few rows carrying a body block. NULL on nearly every row.';

COMMENT ON COLUMN staging.spansh_station_service.latitude IS
'Surface latitude of a planetary port in degrees. Present on a handful of rows only, and meaningless where is_planetary is FALSE.';

COMMENT ON COLUMN staging.spansh_station_service.longitude IS
'Surface longitude of a planetary port in degrees. See latitude: present on a handful of rows only.';

COMMENT ON COLUMN staging.spansh_station_service.has_large_pad IS
'TRUE when the station has at least one large landing pad. The go/no-go for a large ship; large_pads carries how many.';

COMMENT ON COLUMN staging.spansh_station_service.large_pads IS
'Number of large landing pads. NULL where Spansh has no pad breakdown.';

COMMENT ON COLUMN staging.spansh_station_service.medium_pads IS
'Number of medium landing pads. NULL where Spansh has no pad breakdown.';

COMMENT ON COLUMN staging.spansh_station_service.small_pads IS
'Number of small landing pads. NULL where Spansh has no pad breakdown.';

COMMENT ON COLUMN staging.spansh_station_service.has_market IS
'TRUE when the station has a commodity market. The market itself is deliberately not staged -- see the table comment.';

COMMENT ON COLUMN staging.spansh_station_service.has_outfitting IS
'TRUE when the station sells modules. The module list is deliberately not staged.';

COMMENT ON COLUMN staging.spansh_station_service.has_shipyard IS
'TRUE when the station sells ships. The ship list is deliberately not staged.';

COMMENT ON COLUMN staging.spansh_station_service.material_trader IS
'Which materials this trader exchanges: ''Encoded'', ''Manufactured'' or ''Raw''. NULL means the row was pulled for its Technology Broker and has no trader, NOT that the trader''s type is unknown. The per-value counts the API reports sum exactly to the count it reports for the combined filter, which is what makes the partition trustworthy; the stager re-checks that every run, because this is a live query and the totals move daily.';

COMMENT ON COLUMN staging.spansh_station_service.technology_broker IS
'Which unlocks this broker offers: ''Human'' or ''Guardian''. NULL means the row was pulled for its Material Trader and has no broker. The two values partition the broker rows the same way, and the stager checks the sum every run.';

COMMENT ON COLUMN staging.spansh_station_service.services IS
'Every service the station offers, as a list ("Dock", "Refuel", "Material Trader", "Universal Cartographics"). The Material Trader and Technology Broker entries here are what the filter actually matched and must agree with the two columns above. Also the only place Universal Cartographics is recorded, which is the one service an explorer cares about alongside these two.';

COMMENT ON COLUMN staging.spansh_station_service.primary_economy IS
'The station''s dominant economy ("Industrial", "High Tech"). Governs what it stocks, not what it brokers.';

COMMENT ON COLUMN staging.spansh_station_service.secondary_economy IS
'The station''s secondary economy, NULL where it has only one.';

COMMENT ON COLUMN staging.spansh_station_service.government IS
'Government type of the controlling faction ("Democracy", "Corporate"). Volatile: factions change hands.';

COMMENT ON COLUMN staging.spansh_station_service.allegiance IS
'Superpower allegiance ("Federation", "Empire", "Independent"), NULL where Spansh has none. Volatile, and never a permission: allegiance does not gate a trader or a broker.';

COMMENT ON COLUMN staging.spansh_station_service.updated_at IS
'When EDDN last received a report about this station, per Spansh. THE STALENESS SIGNAL: a service is only as real as the last commander who docked and reported it, and an old row here is a claim about the past.';

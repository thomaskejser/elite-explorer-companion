CREATE TABLE IF NOT EXISTS staging.${table} (
    id                  BIGINT,
    name                VARCHAR,
    type                VARCHAR,
    system_id64         BIGINT,
    system_name         VARCHAR,
    x                   DOUBLE,
    y                   DOUBLE,
    z                   DOUBLE,
    distance_to_arrival DOUBLE,
    large_pads          INTEGER,
    medium_pads         INTEGER,
    small_pads          INTEGER,
    services            VARCHAR[],
    update_time         TIMESTAMPTZ
);

COMMENT ON TABLE staging.${table} IS
'RAW SOURCE (not a work table -- never drop or rebuild): every station, settlement, megaship and fleet carrier in Spansh''s galaxy_stations dump, one row per station, read by etl/station/stage.py from the stations of each system and of each of its bodies.

*** WINDOW: ${provenance} ***

A whole-galaxy snapshot of the systems that hold a station, so a station absent here is absent from Spansh, not outside a window. A fleet carrier''s row is where it was last REPORTED (update_time), which can be years old: never read a carrier''s system as its current position without checking update_time.

Downloaded from ${url}.';

COMMENT ON COLUMN staging.${table}.id IS 'Spansh''s station id, which is the game''s MarketID.';
COMMENT ON COLUMN staging.${table}.name IS 'Station name as Spansh spells it; a fleet carrier''s is its callsign.';
COMMENT ON COLUMN staging.${table}.type IS 'Station type: Coriolis Starport, Outpost, Planetary Port, Settlement, Mega ship, Drake-Class Carrier and so on.';
COMMENT ON COLUMN staging.${table}.system_id64 IS 'The game''s id64 of the system, joins main.system_known.system_id.';
COMMENT ON COLUMN staging.${table}.system_name IS 'System name as Spansh spells it.';
COMMENT ON COLUMN staging.${table}.x IS 'System x in ly, Sol-relative.';
COMMENT ON COLUMN staging.${table}.y IS 'System y in ly.';
COMMENT ON COLUMN staging.${table}.z IS 'System z in ly.';
COMMENT ON COLUMN staging.${table}.distance_to_arrival IS 'Light-seconds from the arrival star; 0 for many fleet carriers, which Spansh places at the star.';
COMMENT ON COLUMN staging.${table}.large_pads IS 'Large landing pads; NULL when the dump gives no pad counts.';
COMMENT ON COLUMN staging.${table}.medium_pads IS 'Medium landing pads.';
COMMENT ON COLUMN staging.${table}.small_pads IS 'Small landing pads.';
COMMENT ON COLUMN staging.${table}.services IS 'Station services as the game names them (Universal Cartographics, Vista Genomics, Repair, Restock, Refuel, ...).';
COMMENT ON COLUMN staging.${table}.update_time IS 'When Spansh last received this station''s data.';

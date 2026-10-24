CREATE TABLE IF NOT EXISTS carrier_destination (
    callsign    VARCHAR     NOT NULL PRIMARY KEY,
    destination VARCHAR     NOT NULL,
    set_utc     TIMESTAMPTZ NOT NULL
);

COMMENT ON TABLE carrier_destination IS
'APP STATE: where this commander is sending a fleet carrier, one row per carrier callsign, so the overlay''s Carrier tab and HUD keep the destination across restarts. Written by the overlay when Carrier Route is pressed on the Map tab, replacing that carrier''s row; read at startup, newest row first. Database: elite_mapping_current.duckdb. A destination is an intention, not a record of travel: the carrier''s actual position comes from the journal.';

COMMENT ON COLUMN carrier_destination.callsign IS 'The carrier''s callsign from the journal''s CarrierStats (N1X-G2F); empty when no CarrierStats had been logged when the destination was set.';
COMMENT ON COLUMN carrier_destination.destination IS 'The destination system name, as the Map tab''s sector click copied it.';
COMMENT ON COLUMN carrier_destination.set_utc IS 'When Carrier Route was pressed.';

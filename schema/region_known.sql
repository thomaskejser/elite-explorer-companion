CREATE TABLE IF NOT EXISTS region_known (
    region_id   BIGINT  NOT NULL PRIMARY KEY,
    systems     BIGINT  NOT NULL
);

COMMENT ON TABLE region_known IS
'MIRROR-ONLY, DERIVED: count of main.system_known rows per region_id, so the overlay can show how many systems each region already has on record without reading the 200M-row table. A system on record is one somebody reported to a feed -- not one this commander visited (that is system_visited). Rebuilt whole by etl/refresh_current.py.';

COMMENT ON COLUMN region_known.region_id IS
'References region.region_id.';

COMMENT ON COLUMN region_known.systems IS
'Systems in main.system_known with this region_id, hand-named ones included.';

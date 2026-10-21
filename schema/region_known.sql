-- region_known: how many systems the dumps hold in each galactic region.
--
-- *** THIS TABLE LIVES ONLY IN THE APP-STATE DATABASE, NOT IN THE MODEL. *** It is
-- DERIVED into that file's `model` schema by etl/refresh_current.py from
-- main.system_known, like system_neutron, and this file must exist for that refresh to
-- create it.
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

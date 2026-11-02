CREATE TABLE IF NOT EXISTS staging.${table} (
    system_id64       BIGINT,
    body_name         VARCHAR,
    rotation_period_s DOUBLE,
    region_id         INTEGER,
    x                 DOUBLE,
    y                 DOUBLE,
    z                 DOUBLE
);

COMMENT ON TABLE staging.${table} IS
'RAW SOURCE (FULL catalogue, not a slice): EDAstro''s catalogue of every reported neutron star, downloaded from ${url} by etl/system_body/stage.py. ${provenance}

A NAVIGATION source: neutrons are jet-cone boosts, not discovery targets. Rows merged from here are CATALOGUE-ONLY (source ''edastro_neutron''): they say the star exists, not that the system was scanned.

The arrival-star test is NOT taken from any flag in this file. A primary is the row whose body name equals its system''s full name, derived against main.system_known in the transform.';

COMMENT ON COLUMN staging.${table}.system_id64 IS
'The CSV''s ID64 SystemAddress. It IS main.system_known.system_id.';

COMMENT ON COLUMN staging.${table}.body_name IS
'The CSV''s Name: full body name including the system prefix.';

COMMENT ON COLUMN staging.${table}.rotation_period_s IS
'Rotation period in seconds -- the only rotation data in the database. Not read by any loader.';

COMMENT ON COLUMN staging.${table}.region_id IS
'EDAstro''s region id. Not read by any loader; main.system_known carries the region.';

COMMENT ON COLUMN staging.${table}.x IS
'Galactic x in ly, as EDAstro reports it. Not read by any loader.';

COMMENT ON COLUMN staging.${table}.y IS
'Galactic y in ly. Not read by any loader.';

COMMENT ON COLUMN staging.${table}.z IS
'Galactic z in ly. Not read by any loader.';

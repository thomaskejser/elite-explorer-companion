CREATE TABLE IF NOT EXISTS staging.${table} (
    name   VARCHAR,
    id     BIGINT,
    id64   BIGINT,
    coords STRUCT(x DOUBLE, y DOUBLE, z DOUBLE),
    date   TIMESTAMP
);

COMMENT ON TABLE staging.${table} IS
'RAW SOURCE (not a work table -- never drop or rebuild): EDSM systems with coordinates, downloaded whole and read with read_json_auto by etl/system_known/stage.py.

*** WINDOW: ${provenance} ***

Origin of most name and coordinate resolution, and of the ~2.9M systems Spansh does not carry -- which is the entire reason it is staged alongside a source 20 times its size. It has NO body data and no body count; anything about bodies comes from Spansh.

Downloaded from ${url}.';

COMMENT ON COLUMN staging.${table}.name IS
'Full system name as EDSM spells it, sector prefix included. Spellings differ from Spansh on a small number of systems ("CoRoT-9" against "Corot-9"), which is how duplicate rows enter system_known -- match on id64 where you can.';

COMMENT ON COLUMN staging.${table}.id IS
'EDSM''s OWN internal row id. Meaningless outside EDSM, joins to nothing here, and must never be confused with id64.';

COMMENT ON COLUMN staging.${table}.id64 IS
'The GAME''s 64-bit system address. The one join that is safe against every other source.';

COMMENT ON COLUMN staging.${table}.coords IS
'STRUCT of x, y, z in ly, Sol-relative, kept in the shape the dump publishes rather than flattened -- staging holds what was downloaded. Read as coords.x. Rows without coordinates are not in this feed at all, which is what the filename means.';

COMMENT ON COLUMN staging.${table}.date IS
'When EDSM last saw the system change. In a DELTA window every row is inside the window by construction.';

CREATE TABLE IF NOT EXISTS staging.${table} (
    system_id64        BIGINT,
    body_no            INTEGER,
    name               VARCHAR,
    sub_type           VARCHAR,
    earth_masses       DOUBLE,
    terraforming_state VARCHAR
);

COMMENT ON TABLE staging.${table} IS
'RAW SOURCE (INCREMENTAL DELTA -- NOT a catalogue): EDAstro planets, downloaded from ${url} by etl/system_body/stage.py and reduced to the columns main.system_body reads.

*** WINDOW: ${provenance} *** EDAstro publishes this at one width only. Never fit a rate or quote a census from it.

PLANETS ONLY -- the feed carries no star rows, so every row is merged as type ''planet''. Lowest priority of the scanned feeds: used only for a (system, body name) neither Spansh nor EDSM reports.';

COMMENT ON COLUMN staging.${table}.system_id64 IS
'The game''s system address, from systemId64. It IS main.system_known.system_id.';

COMMENT ON COLUMN staging.${table}.body_no IS
'The body''s index within its system, from EDAstro bodyId -- the same index Spansh and the game use, so it is main.system_body.body_no. *** NOT body_id, which is the body TYPE. *** NULL where EDAstro omits it.';

COMMENT ON COLUMN staging.${table}.name IS
'Full body name including the system prefix.';

COMMENT ON COLUMN staging.${table}.sub_type IS
'EDAstro subType, matched verbatim against main.body.body for type ''planet''.';

COMMENT ON COLUMN staging.${table}.earth_masses IS
'Mass in Earth masses.';

COMMENT ON COLUMN staging.${table}.terraforming_state IS
'Only the exact value ''Terraformable'' counts as terraformable.';

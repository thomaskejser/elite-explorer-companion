CREATE TABLE IF NOT EXISTS staging.${table} (
    system_id64        BIGINT,
    body_no            INTEGER,
    name               VARCHAR,
    type               VARCHAR,
    sub_type           VARCHAR,
    is_main_star       BOOLEAN,
    solar_masses       DOUBLE,
    earth_masses       DOUBLE,
    terraforming_state VARCHAR
);

COMMENT ON TABLE staging.${table} IS
'RAW SOURCE (INCREMENTAL DELTA -- NOT a catalogue): EDSM bodies, downloaded from ${url} by etl/system_body/stage.py and reduced to the columns main.system_body reads.

*** WINDOW: ${provenance} *** EDSM publishes NO full body dump, so this is all EDSM body data this project can have. Never fit a rate or quote a census from it.

Superseded by the Spansh body dump wherever both hold a body: transform.system_body takes EDSM only for a body Spansh does not report.';

COMMENT ON COLUMN staging.${table}.system_id64 IS
'The game''s system address, from systemId64. It IS main.system_known.system_id, so it joins with no bridge.';

COMMENT ON COLUMN staging.${table}.body_no IS
'The body''s index within its system, from EDSM bodyId -- the same index Spansh and the game use, so it is main.system_body.body_no. *** NOT body_id, which is the body TYPE. *** NULL where EDSM omits it.';

COMMENT ON COLUMN staging.${table}.name IS
'Full body name INCLUDING the system prefix (''Sol 3''). The designation main.system_body stores is this with the system name stripped.';

COMMENT ON COLUMN staging.${table}.type IS
'''Star'' or ''Planet'' as EDSM spells it; lower-cased before it is matched against main.body.type.';

COMMENT ON COLUMN staging.${table}.sub_type IS
'EDSM subType, matched verbatim against main.body.body. An unmatched spelling leaves body_id NULL (type unknown), never drops the body.';

COMMENT ON COLUMN staging.${table}.is_main_star IS
'EDSM isMainStar: the arrival star. NULL is read as FALSE.';

COMMENT ON COLUMN staging.${table}.solar_masses IS
'Stars only. NULL for planets.';

COMMENT ON COLUMN staging.${table}.earth_masses IS
'Planets only. NULL for stars.';

COMMENT ON COLUMN staging.${table}.terraforming_state IS
'EDSM terraformingState; only the exact value ''Terraformable'' counts as terraformable.';

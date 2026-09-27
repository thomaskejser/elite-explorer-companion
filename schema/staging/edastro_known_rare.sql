CREATE TABLE IF NOT EXISTS staging.${table} (
    system_name   VARCHAR,
    body_name     VARCHAR,
    kind          VARCHAR,
    is_main_star  BOOLEAN,
    mass_code     VARCHAR,
    star_type     VARCHAR,
    scanned_at    VARCHAR,
    discovered_at VARCHAR
);

COMMENT ON TABLE staging.${table} IS
'RAW SOURCE (FULL catalogue, not a slice): EDAstro''s per-class catalogues of every black hole and Wolf-Rayet star ever reported, downloaded from ${url} by etl/system_body/stage.py and unioned. ${provenance}

One row per (system, star, kind). Complete for its two classes, which is what makes it an EXCLUSION signal as well as a source of bodies: a system in here is known to hold the star, whether or not any scan dump reports its bodies.

*** NO id64. *** The CSVs carry names only, so transform.system_body_rare resolves system_name against main.system_known and drops any name that resolves to more than one system (1,477 full names belong to several). Rows merged from here are CATALOGUE-ONLY (source ''edastro_rare''): they say the star exists, not that the system was scanned.';

COMMENT ON COLUMN staging.${table}.system_name IS
'The CSV''s System column: the full system name, used for the name-to-id resolution.';

COMMENT ON COLUMN staging.${table}.body_name IS
'The CSV''s Star column: the full body name including the system prefix (''1 Vulpeculae B'').';

COMMENT ON COLUMN staging.${table}.kind IS
'''black_hole'' or ''wolf_rayet'': which of the two CSVs the row came from.';

COMMENT ON COLUMN staging.${table}.is_main_star IS
'The CSV''s Main Star = ''yes''. max() across the (system, star, kind) group.';

COMMENT ON COLUMN staging.${table}.mass_code IS
'Boxel mass code letter from the CSV, blank as NULL. Not read by any loader.';

COMMENT ON COLUMN staging.${table}.star_type IS
'The CSV''s Type (''Black Hole'', ''Wolf-Rayet C Star''), matched verbatim against main.body.body for type ''star''.';

COMMENT ON COLUMN staging.${table}.scanned_at IS
'The CSV''s Timestamp, as text: when EDAstro last saw the star reported. Not a discovery date.';

COMMENT ON COLUMN staging.${table}.discovered_at IS
'The CSV''s EDSM Discovery Date, as text, populated on a minority of rows. The ONLY discovery date any source here carries; becomes main.system_body.discovered_time on insert.';

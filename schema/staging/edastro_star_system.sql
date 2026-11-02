CREATE TABLE IF NOT EXISTS staging.${table} (
    id             BIGINT,
    id64           BIGINT,
    name           VARCHAR,
    coords         STRUCT(x DOUBLE, y DOUBLE, z DOUBLE),
    region         INTEGER,
    main_star_type VARCHAR,
    body_count     INTEGER,
    non_body_count INTEGER,
    fss_progress   DOUBLE,
    sol_dist       DOUBLE,
    edsm_id        BIGINT,
    eddb_id        BIGINT,
    date_added     TIMESTAMP,
    update_time    TIMESTAMP
);

COMMENT ON TABLE staging.${table} IS
'RAW SOURCE (not a work table -- never drop or rebuild): EDAstro systems, downloaded whole and read with read_json_auto by etl/system_known/stage.py.

*** WINDOW: ${provenance} *** EDAstro publishes NO full system dump and no other width, so this is the only window there is and no --window value can widen it. ~99.1% a SUBSET of EDSM rather than a superset: it is staged for the two columns nothing else carries, `region` and `main_star_type`, not for coverage.

Downloaded from ${url}.';

COMMENT ON COLUMN staging.${table}.id IS 'EDAstro''s own row id. Internal to EDAstro, joins to nothing here.';
COMMENT ON COLUMN staging.${table}.id64 IS 'The GAME''s 64-bit system address, the safe join to every other source.';
COMMENT ON COLUMN staging.${table}.name IS 'Full system name as EDAstro spells it, sector prefix included.';
COMMENT ON COLUMN staging.${table}.coords IS 'STRUCT of x, y, z in ly, Sol-relative, as the feed publishes it. Read as coords.x.';
COMMENT ON COLUMN staging.${table}.region IS
'The GAME''s region id, 1..42 -- the ONLY per-system region label any feed here carries. Everything else has to infer region from the sector, so this is what the inference is checked against. NOT a region NAME; join main.region on region_id.';
COMMENT ON COLUMN staging.${table}.main_star_type IS
'ARRIVAL star type as a full sub_type string ("F (White) Star"), matching main.body.body on 41 of the 42 values seen. The only arrival-star source that does not require the Spansh body dump. GOTCHA: it is the ARRIVAL star, so it does not say what else the system contains.';
COMMENT ON COLUMN staging.${table}.body_count IS 'Bodies EDAstro knows in the system. NOT the declared count from the honk -- that is spansh declared_body_count, and this can be lower.';
COMMENT ON COLUMN staging.${table}.non_body_count IS 'Non-body signal sources counted in the system. Not comparable with body_count and not part of it.';
COMMENT ON COLUMN staging.${table}.fss_progress IS 'Fraction of the FSS sweep EDAstro believes is complete, 0..1. A COVERAGE measure of reports, so it carries discovery bias and must not be read as a property of the system.';
COMMENT ON COLUMN staging.${table}.sol_dist IS 'Distance from Sol in ly, derivable from coords and kept only because the feed carries it.';
COMMENT ON COLUMN staging.${table}.edsm_id IS 'EDSM''s internal id for the same system, when EDAstro knows it. Cross-reference only -- not id64.';
COMMENT ON COLUMN staging.${table}.eddb_id IS 'EDDB''s internal id. EDDB IS DEFUNCT, so this is historical and joins to nothing this project holds.';
COMMENT ON COLUMN staging.${table}.date_added IS 'When EDAstro first saw the system. A DISCOVERY date for EDAstro, not for the galaxy.';
COMMENT ON COLUMN staging.${table}.update_time IS 'When EDAstro last saw the system change. In a delta window every row is inside the window by construction.';

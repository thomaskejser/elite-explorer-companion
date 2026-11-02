CREATE TABLE IF NOT EXISTS seed_info (
    id          VARCHAR      NOT NULL,
    built_utc   TIMESTAMPTZ  NOT NULL
);

COMMENT ON TABLE seed_info IS
'SEED-ONLY: one row naming the build of the model mirror in this file. etl/refresh_current.py writes it last into seed/elite_mapping_seed.duckdb; the overlay copies it into the app-state file with the rest of the model schema, and reloads that schema from a seed whose id differs. Not a history: a reload replaces the row.';

COMMENT ON COLUMN seed_info.id IS
'Random identifier of this build. Equal ids mean the same mirror; nothing else may be read from it.';

COMMENT ON COLUMN seed_info.built_utc IS
'When etl/refresh_current.py finished writing this mirror, in UTC.';

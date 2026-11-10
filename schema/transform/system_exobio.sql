CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.system_exobio;

CREATE TABLE transform.system_exobio (
    system_id        BIGINT  NOT NULL PRIMARY KEY,
    system           VARCHAR NOT NULL,
    x                DOUBLE,
    y                DOUBLE,
    z                DOUBLE,
    candidate_bodies INTEGER NOT NULL,
    unmapped_bodies  INTEGER NOT NULL,
    worked_bodies    INTEGER NOT NULL,
    cr_expected      BIGINT  NOT NULL,
    best_body        VARCHAR NOT NULL,
    best_cr          BIGINT  NOT NULL,
    best_species     VARCHAR,
    last_reported    TIMESTAMPTZ NOT NULL
);

COMMENT ON TABLE transform.system_exobio IS
'TRANSFORM: main.system_exobio as this load computes it from transform.exobio_body and main.exobio_odds. Rebuilt on every load, safe to drop. See main.system_exobio for what each column means.';
COMMENT ON COLUMN transform.system_exobio.system_id IS 'The system''s id64; the merge key.';
COMMENT ON COLUMN transform.system_exobio.system IS 'Full system name, composed from main.system_known and main.sector.';
COMMENT ON COLUMN transform.system_exobio.x IS 'Galactic x, ly.';
COMMENT ON COLUMN transform.system_exobio.y IS 'Galactic y, ly.';
COMMENT ON COLUMN transform.system_exobio.z IS 'Galactic z, ly.';
COMMENT ON COLUMN transform.system_exobio.candidate_bodies IS 'Bodies valued: unmapped, pre_odyssey or stale_landable.';
COMMENT ON COLUMN transform.system_exobio.unmapped_bodies IS 'Of those, bodies with a reported biology signal.';
COMMENT ON COLUMN transform.system_exobio.worked_bodies IS 'Bodies in the system already mapped or codexed.';
COMMENT ON COLUMN transform.system_exobio.cr_expected IS 'Sum of the candidate bodies'' expected base value, credits.';
COMMENT ON COLUMN transform.system_exobio.best_body IS 'Full name of the most valuable candidate body.';
COMMENT ON COLUMN transform.system_exobio.best_cr IS 'Its expected base value, credits.';
COMMENT ON COLUMN transform.system_exobio.best_species IS 'Its cell''s likely_species.';
COMMENT ON COLUMN transform.system_exobio.last_reported IS 'Latest report on any candidate body.';

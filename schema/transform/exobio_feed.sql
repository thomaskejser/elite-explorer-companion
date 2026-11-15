CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.exobio_feed;

CREATE TABLE transform.exobio_feed (
    system_id64     BIGINT NOT NULL,
    name            VARCHAR NOT NULL,
    sub_type        VARCHAR NOT NULL,
    atmosphere_type VARCHAR NOT NULL,
    surface_temp_k  DOUBLE,
    is_landable     BOOLEAN,
    signal_biology  INTEGER,
    has_genus       BOOLEAN NOT NULL,
    updated         TIMESTAMPTZ NOT NULL
);

COMMENT ON TABLE transform.exobio_feed IS
'TRANSFORM: every report of a solid planet with a thin atmosphere in staging.spansh_galaxy_body and in whichever of the 1-month and 1-day deltas are staged, unreduced -- a body reported by two feeds has two rows. Filled one feed at a time by etl/exobio_odds/feed.sql, in one pass over each so etl/exobio_odds/body.sql can reduce it in buckets without rescanning 570M staged bodies per bucket. Rebuilt by etl/exobio_odds/load.py, safe to drop.';
COMMENT ON COLUMN transform.exobio_feed.system_id64 IS 'The system''s id64.';
COMMENT ON COLUMN transform.exobio_feed.name IS 'Full body name, system prefix included.';
COMMENT ON COLUMN transform.exobio_feed.sub_type IS 'Spansh sub_type, one of the five solid types.';
COMMENT ON COLUMN transform.exobio_feed.atmosphere_type IS 'Spansh atmosphere_type, always beginning ''Thin''.';
COMMENT ON COLUMN transform.exobio_feed.surface_temp_k IS 'Surface temperature, kelvin.';
COMMENT ON COLUMN transform.exobio_feed.is_landable IS 'Spansh is_landable in this report.';
COMMENT ON COLUMN transform.exobio_feed.signal_biology IS 'Biology signal count in this report; NULL when none was reported.';
COMMENT ON COLUMN transform.exobio_feed.has_genus IS 'TRUE when this report lists genera, which only a surface map reveals.';
COMMENT ON COLUMN transform.exobio_feed.updated IS 'Spansh update_time of this report.';

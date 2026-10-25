CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.exobio_body;

CREATE TABLE transform.exobio_body (
    system_id   BIGINT  NOT NULL,
    body        VARCHAR NOT NULL,
    body_type   VARCHAR NOT NULL,
    atmosphere  VARCHAR NOT NULL,
    temp_k      DOUBLE,
    temp_band   INTEGER,
    star        VARCHAR NOT NULL,
    landable    BOOLEAN,
    bio_signals INTEGER,
    updated     TIMESTAMPTZ NOT NULL,
    status      VARCHAR NOT NULL CHECK (status IN ('codexed', 'mapped', 'unmapped',
                                                   'pre_odyssey', 'stale_landable', 'unreported'))
);

COMMENT ON TABLE transform.exobio_body IS
'TRANSFORM: every solid planet with a thin atmosphere in the Spansh body feeds, one row per body at its most recent report, with what is known about its biology. The input to main.exobio_odds and main.system_exobio; each of their loaders rebuilds it. Safe to drop.

SOURCES. staging.spansh_galaxy_body (the full catalogue) plus the 1-month and 1-day deltas, latest update_time winning, so a body rescanned since the catalogue was cut carries its new signals. Solid types only (high metal content, rocky, icy, rocky ice, metal-rich); water and ammonia worlds are never landable.

*** NOT EVERY BIOLOGY BODY. *** Airless landable bodies carry the Horizons organisms (brain trees, anemones, shards, tubers) on about 0.2% of bodies at about 1.5M credits each, and are left out.

STATUS, the first that applies:
  codexed        -- staging.canonn_codex_event reports a biology sighting on this body: somebody has been on the surface.
  mapped         -- Spansh lists its genera, which only a surface map reveals.
  unmapped       -- a biology signal count is reported and the genera are not: seen from orbit, never mapped.
  pre_odyssey    -- last reported before Odyssey (2021-05-19), when no thin-atmosphere body was landable and no biology signal existed to report.
  stale_landable -- reported since, but its landable flag is not TRUE: the record still carries a pre-Odyssey scan.
  unreported     -- landable and reported since Odyssey with no biology signal. Treated as no biology, which is wrong about one time in six: many scanners never send the signal count.';

COMMENT ON COLUMN transform.exobio_body.system_id IS 'The system''s id64 -- main.system_known.system_id.';
COMMENT ON COLUMN transform.exobio_body.body IS 'Full body name as Spansh spells it, system prefix included. With system_id, the key.';
COMMENT ON COLUMN transform.exobio_body.body_type IS 'Spansh sub_type, e.g. ''High metal content world''.';
COMMENT ON COLUMN transform.exobio_body.atmosphere IS 'Spansh atmosphere_type, e.g. ''Thin Carbon dioxide''. The journal spells the same thing ''thin carbon dioxide atmosphere''.';
COMMENT ON COLUMN transform.exobio_body.temp_k IS 'Surface temperature, kelvin.';
COMMENT ON COLUMN transform.exobio_body.temp_band IS 'floor(temp_k / 20) * 20, clamped to 100..440: the temperature cell main.exobio_odds is keyed on. NULL where the temperature is unknown.';
COMMENT ON COLUMN transform.exobio_body.star IS 'main.body.code of the system''s ARRIVAL star (''K'', ''DA'', ''M_RedGiant''), ''?'' where the model does not know it. Not necessarily the star the body orbits.';
COMMENT ON COLUMN transform.exobio_body.landable IS 'Spansh is_landable as last reported.';
COMMENT ON COLUMN transform.exobio_body.bio_signals IS 'Biology signal count. NULL means none was REPORTED, which is not the same as none.';
COMMENT ON COLUMN transform.exobio_body.updated IS 'When Spansh last received data for the body.';
COMMENT ON COLUMN transform.exobio_body.status IS 'What is known about the body''s biology; see the table comment for the six values.';

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

INSERT INTO transform.system_exobio
WITH candidate AS (
    SELECT b.system_id, b.body, b.status, b.updated,
           coalesce(CASE WHEN o.bodies >= 200 THEN o.p_bio END, w.p_bio) AS p_bio,
           coalesce(CASE WHEN o.codexed_bodies >= 20 THEN o.cr_species END, w.cr_species) AS cr_species,
           coalesce(CASE WHEN o.bodies >= 200 THEN o.cr_bio END, w.cr_bio) AS cr_bio,
           coalesce(CASE WHEN o.codexed_bodies >= 20 THEN o.likely_species END, w.likely_species) AS likely_species,
           b.bio_signals
    FROM transform.exobio_body b
    LEFT JOIN main.exobio_odds o
      ON o.atmosphere = b.atmosphere AND o.body_type = b.body_type
     AND o.temp_band = b.temp_band AND o.star = b.star
    LEFT JOIN main.exobio_odds w
      ON w.atmosphere = b.atmosphere AND w.body_type = b.body_type
     AND w.temp_band = b.temp_band AND w.star = '*'
    WHERE b.status IN ('unmapped', 'pre_odyssey', 'stale_landable')
),
valued AS (
    SELECT *, CAST(round(CASE WHEN status = 'unmapped' THEN bio_signals * cr_species
                              ELSE p_bio * cr_bio END) AS BIGINT) AS cr_body
    FROM candidate
),
worked AS (
    SELECT system_id, count(*) AS n
    FROM transform.exobio_body
    WHERE status IN ('codexed', 'mapped')
    GROUP BY 1
),
per_system AS (
    SELECT system_id,
           count(*) AS candidate_bodies,
           count(*) FILTER (WHERE status = 'unmapped') AS unmapped_bodies,
           sum(coalesce(cr_body, 0)) AS cr_expected,
           arg_max(body, (coalesce(cr_body, 0), body)) AS best_body,
           max(coalesce(cr_body, 0)) AS best_cr,
           arg_max(likely_species, (coalesce(cr_body, 0), body)) AS best_species,
           max(updated) AS last_reported
    FROM valued
    GROUP BY 1
    HAVING sum(coalesce(cr_body, 0)) >= 10000000
)
SELECT p.system_id,
       CASE WHEN k.sector_id = 0 OR sc.sector IS NULL THEN k.system_in_sector
            ELSE sc.sector || ' ' || k.system_in_sector END,
       k.x, k.y, k.z,
       p.candidate_bodies, p.unmapped_bodies, coalesce(w.n, 0),
       p.cr_expected, p.best_body, p.best_cr, p.best_species, p.last_reported
FROM per_system p
JOIN main.system_known k ON k.system_id = p.system_id
LEFT JOIN main.sector sc ON sc.sector_id = k.sector_id
LEFT JOIN worked w ON w.system_id = p.system_id;

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

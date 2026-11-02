CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.exobio_odds;

CREATE TABLE transform.exobio_odds (
    atmosphere     VARCHAR NOT NULL,
    body_type      VARCHAR NOT NULL,
    temp_band      INTEGER NOT NULL,
    star           VARCHAR NOT NULL,
    bodies         BIGINT  NOT NULL,
    p_bio          DOUBLE  NOT NULL CHECK (p_bio BETWEEN 0 AND 1),
    signals_bio    DOUBLE,
    codexed_bodies BIGINT  NOT NULL,
    cr_species     BIGINT,
    cr_bio         BIGINT,
    likely_species VARCHAR,
    PRIMARY KEY (atmosphere, body_type, temp_band, star)
);

INSERT INTO transform.exobio_odds
WITH fit AS (
    SELECT atmosphere, body_type, temp_band, star,
           status = 'codexed' OR coalesce(bio_signals, 0) > 0 AS has_bio, bio_signals
    FROM transform.exobio_body
    WHERE temp_band IS NOT NULL AND landable
      AND updated >= TIMESTAMPTZ '2021-05-19 00:00:00+00'
      AND status IN ('codexed', 'mapped', 'unmapped', 'unreported')
),
rate AS (
    SELECT atmosphere, body_type, temp_band, coalesce(star, '*') AS star,
           count(*) AS bodies,
           round(avg(has_bio::INTEGER), 4) AS p_bio,
           round(avg(bio_signals) FILTER (WHERE bio_signals > 0), 3) AS signals_bio
    FROM fit
    GROUP BY GROUPING SETS ((atmosphere, body_type, temp_band, star),
                            (atmosphere, body_type, temp_band))
),
sighting AS (
    SELECT DISTINCT b.atmosphere, b.body_type, b.temp_band, b.star, b.system_id, b.body,
           s.species, s.cr_value
    FROM transform.exobio_body b
    JOIN staging.canonn_codex_event c
      ON c.id64 = b.system_id AND c.body = b.body AND c.hud_category = 'Biology'
    JOIN main.exobio_species s ON s.species = split_part(c.english_name, ' - ', 1)
    WHERE b.temp_band IS NOT NULL
),
codex AS (
    SELECT atmosphere, body_type, temp_band, coalesce(star, '*') AS star,
           count(DISTINCT (system_id, body)) AS codexed_bodies,
           round(avg(cr_value)) AS cr_species
    FROM sighting
    GROUP BY GROUPING SETS ((atmosphere, body_type, temp_band, star),
                            (atmosphere, body_type, temp_band))
),
per_species AS (
    SELECT atmosphere, body_type, temp_band, coalesce(star, '*') AS star, species,
           count(DISTINCT (system_id, body)) AS n
    FROM sighting
    GROUP BY GROUPING SETS ((atmosphere, body_type, temp_band, star, species),
                            (atmosphere, body_type, temp_band, species))
),
likely AS (
    SELECT atmosphere, body_type, temp_band, star,
           string_agg(species || ' ' || CAST(round(100.0 * n / codexed_bodies) AS INTEGER) || '%',
                      ', ' ORDER BY n DESC, species) AS likely_species
    FROM (SELECT p.*, c.codexed_bodies
          FROM per_species p
          JOIN codex c USING (atmosphere, body_type, temp_band, star)
          WHERE p.n * 20 >= c.codexed_bodies
          QUALIFY row_number() OVER (PARTITION BY p.atmosphere, p.body_type, p.temp_band, p.star
                                     ORDER BY p.n DESC, p.species) <= 3)
    GROUP BY atmosphere, body_type, temp_band, star
)
SELECT r.atmosphere, r.body_type, r.temp_band, r.star, r.bodies, r.p_bio, r.signals_bio,
       coalesce(c.codexed_bodies, 0), c.cr_species,
       CAST(round(r.signals_bio * c.cr_species) AS BIGINT), l.likely_species
FROM rate r
LEFT JOIN codex c USING (atmosphere, body_type, temp_band, star)
LEFT JOIN likely l USING (atmosphere, body_type, temp_band, star);

COMMENT ON TABLE transform.exobio_odds IS
'TRANSFORM: main.exobio_odds as this load computes it from transform.exobio_body, staging.canonn_codex_event and main.exobio_species. Rebuilt on every load, safe to drop. See main.exobio_odds for what each column means.';
COMMENT ON COLUMN transform.exobio_odds.atmosphere IS 'Spansh atmosphere_type. Key part.';
COMMENT ON COLUMN transform.exobio_odds.body_type IS 'Spansh sub_type. Key part.';
COMMENT ON COLUMN transform.exobio_odds.temp_band IS 'Temperature cell, kelvin; see transform.exobio_body.temp_band. Key part.';
COMMENT ON COLUMN transform.exobio_odds.star IS 'Arrival-star code, or ''*'' for the cell over every star. Key part.';
COMMENT ON COLUMN transform.exobio_odds.bodies IS 'Odyssey-era landable bodies the rate is fitted on.';
COMMENT ON COLUMN transform.exobio_odds.p_bio IS 'Share of them reporting biology, 4 dp.';
COMMENT ON COLUMN transform.exobio_odds.signals_bio IS 'Mean biology signal count where there is one, 3 dp.';
COMMENT ON COLUMN transform.exobio_odds.codexed_bodies IS 'Bodies in the cell with a Canonn species sighting.';
COMMENT ON COLUMN transform.exobio_odds.cr_species IS 'Mean base value of a sighted species, credits.';
COMMENT ON COLUMN transform.exobio_odds.cr_bio IS 'signals_bio * cr_species, credits.';
COMMENT ON COLUMN transform.exobio_odds.likely_species IS 'The up to three most-sighted species carried by at least 5% of codexed bodies, with their share.';

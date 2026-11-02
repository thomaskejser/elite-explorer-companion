CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.exobio_genus_odds;

CREATE TABLE transform.exobio_genus_odds (
    atmosphere     VARCHAR NOT NULL,
    body_type      VARCHAR NOT NULL,
    temp_band      INTEGER NOT NULL,
    star           VARCHAR NOT NULL,
    genus          VARCHAR NOT NULL,
    genus_key      VARCHAR NOT NULL,
    bodies         BIGINT  NOT NULL,
    share          DOUBLE  NOT NULL CHECK (share BETWEEN 0 AND 1),
    cr_genus       BIGINT  NOT NULL,
    PRIMARY KEY (atmosphere, body_type, temp_band, star, genus)
);

INSERT INTO transform.exobio_genus_odds
WITH sighting AS (
    SELECT DISTINCT b.atmosphere, b.body_type, b.temp_band, b.star, b.system_id, b.body,
           s.species, s.genus, s.genus_key, s.cr_value
    FROM transform.exobio_body b
    JOIN staging.canonn_codex_event c
      ON c.id64 = b.system_id AND c.body = b.body AND c.hud_category = 'Biology'
    JOIN main.exobio_species s ON s.species = split_part(c.english_name, ' - ', 1)
    WHERE b.temp_band IS NOT NULL
),
cell AS (
    SELECT atmosphere, body_type, temp_band, coalesce(star, '*') AS star,
           count(DISTINCT (system_id, body)) AS codexed_bodies
    FROM sighting
    GROUP BY GROUPING SETS ((atmosphere, body_type, temp_band, star),
                            (atmosphere, body_type, temp_band))
),
per_genus AS (
    SELECT atmosphere, body_type, temp_band, coalesce(star, '*') AS star, genus,
           min(genus_key) AS genus_key,
           count(DISTINCT (system_id, body)) AS bodies,
           round(avg(cr_value)) AS cr_genus
    FROM sighting
    GROUP BY GROUPING SETS ((atmosphere, body_type, temp_band, star, genus),
                            (atmosphere, body_type, temp_band, genus))
)
SELECT g.atmosphere, g.body_type, g.temp_band, g.star, g.genus, g.genus_key, g.bodies,
       round(g.bodies / c.codexed_bodies, 4), CAST(g.cr_genus AS BIGINT)
FROM per_genus g
JOIN cell c USING (atmosphere, body_type, temp_band, star);

COMMENT ON TABLE transform.exobio_genus_odds IS
'TRANSFORM: main.exobio_genus_odds as this load computes it from transform.exobio_body, staging.canonn_codex_event and main.exobio_species. Rebuilt on every load, safe to drop. See main.exobio_genus_odds for what each column means.';
COMMENT ON COLUMN transform.exobio_genus_odds.atmosphere IS 'Spansh atmosphere_type. Key part.';
COMMENT ON COLUMN transform.exobio_genus_odds.body_type IS 'Spansh sub_type. Key part.';
COMMENT ON COLUMN transform.exobio_genus_odds.temp_band IS 'Temperature cell, kelvin. Key part.';
COMMENT ON COLUMN transform.exobio_genus_odds.star IS 'Arrival-star code, or ''*'' for the cell over every star. Key part.';
COMMENT ON COLUMN transform.exobio_genus_odds.genus IS 'main.exobio_species.genus. Key part.';
COMMENT ON COLUMN transform.exobio_genus_odds.genus_key IS 'main.exobio_species.genus_key, the codex token.';
COMMENT ON COLUMN transform.exobio_genus_odds.bodies IS 'Codexed bodies in the cell with a sighting of this genus.';
COMMENT ON COLUMN transform.exobio_genus_odds.share IS 'bodies over the cell''s codexed bodies, 4 dp.';
COMMENT ON COLUMN transform.exobio_genus_odds.cr_genus IS 'Mean base value of the genus''s species sighted in the cell, credits.';

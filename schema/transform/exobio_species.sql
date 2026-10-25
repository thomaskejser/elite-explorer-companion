CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.exobio_species;

CREATE TABLE transform.exobio_species (
    species_key    VARCHAR NOT NULL PRIMARY KEY CHECK (species_key LIKE '$Codex_Ent_%'),
    genus_key      VARCHAR NOT NULL CHECK (genus_key LIKE '$Codex_Ent_%'),
    species        VARCHAR NOT NULL UNIQUE CHECK (trim(species) <> ''),
    genus          VARCHAR NOT NULL CHECK (trim(genus) <> ''),
    cr_value       BIGINT  NOT NULL CHECK (cr_value > 0),
    colony_m       INTEGER CHECK (colony_m > 0),
    bodies_codexed BIGINT  NOT NULL
);

INSERT INTO transform.exobio_species
WITH codexed AS (
    SELECT split_part(english_name, ' - ', 1) AS species, count(DISTINCT (id64, body)) AS n
    FROM staging.canonn_codex_event
    WHERE hud_category = 'Biology' AND body IS NOT NULL
    GROUP BY 1
)
SELECT c.species_key, c.genus_key, c.species, c.genus, c.cr_value, c.colony_m,
       coalesce(x.n, 0)
FROM staging.exobio_species_curated c
LEFT JOIN codexed x USING (species);

COMMENT ON TABLE transform.exobio_species IS
'TRANSFORM: staging.exobio_species_curated validated against the constraints main.exobio_species needs, with bodies_codexed counted from staging.canonn_codex_event. Rebuilt on every load, safe to drop.';
COMMENT ON COLUMN transform.exobio_species.species_key IS 'The game''s species codex token; the merge key.';
COMMENT ON COLUMN transform.exobio_species.genus_key IS 'The game''s genus codex token.';
COMMENT ON COLUMN transform.exobio_species.species IS 'English species name, Canonn spelling, unique.';
COMMENT ON COLUMN transform.exobio_species.genus IS 'English genus name.';
COMMENT ON COLUMN transform.exobio_species.cr_value IS 'Vista Genomics base value in credits.';
COMMENT ON COLUMN transform.exobio_species.colony_m IS 'Minimum metres between samples of the genus.';
COMMENT ON COLUMN transform.exobio_species.bodies_codexed IS 'Distinct Canonn-reported bodies carrying the species; see main.exobio_species.bodies_codexed.';

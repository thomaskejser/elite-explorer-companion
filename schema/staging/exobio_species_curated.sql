CREATE TABLE IF NOT EXISTS staging.exobio_species_curated (
    species     VARCHAR,
    genus       VARCHAR,
    species_key VARCHAR,
    genus_key   VARCHAR,
    cr_value    BIGINT,
    colony_m    INTEGER
);

COMMENT ON TABLE staging.exobio_species_curated IS
'RAW SOURCE (not a work table): input/exobio_species.parquet copied in whole by etl/exobio_species/stage.py. The file is AUTHORITATIVE and hand-edited, so this is the species vocabulary exactly as a person last left it. Seeded once by etl/exobio_species/seed.py, which refuses to overwrite the file; restore it from git.';

COMMENT ON COLUMN staging.exobio_species_curated.species IS 'English species name, Canonn spelling. See main.exobio_species.species.';
COMMENT ON COLUMN staging.exobio_species_curated.genus IS 'English genus name. See main.exobio_species.genus.';
COMMENT ON COLUMN staging.exobio_species_curated.species_key IS 'The game''s species codex token, the key main.exobio_species merges on.';
COMMENT ON COLUMN staging.exobio_species_curated.genus_key IS 'The game''s genus codex token.';
COMMENT ON COLUMN staging.exobio_species_curated.cr_value IS 'Vista Genomics base value in credits, as curated. See main.exobio_species.cr_value.';
COMMENT ON COLUMN staging.exobio_species_curated.colony_m IS 'Minimum metres between samples of the genus, as curated.';

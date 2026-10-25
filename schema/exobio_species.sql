CREATE TABLE IF NOT EXISTS exobio_species (
    species_key    VARCHAR NOT NULL PRIMARY KEY,
    genus_key      VARCHAR NOT NULL,
    species        VARCHAR NOT NULL,
    genus          VARCHAR NOT NULL,
    cr_value       BIGINT  NOT NULL,
    colony_m       INTEGER,
    bodies_codexed BIGINT  NOT NULL
);

COMMENT ON TABLE exobio_species IS
'REFERENCE DIMENSION: one row per exobiology SPECIES the game can log (118: the 22 Odyssey and Horizons genera), with what Vista Genomics pays for it.

AUTHORITY AND LOADING. input/exobio_species.parquet is AUTHORITATIVE and safe to hand-edit; this table is a MERGE TARGET loaded by etl/exobio_species/refresh.py, matched on species_key, never dropped or replaced. A row absent from the parquet is left in place and reported.

WHERE IT COMES FROM. etl/exobio_species/seed.py wrote the parquet once from two GPL-2.0 EDMC plugins by Silarn: the species names, codex tokens and values from EDMC-BioScan''s rulesets (src/bio_scan/bio_data/rulesets/*.py and species.py), and the genus names and colony distances from EDMC-ExploData (src/ExploData/explo_data/bio_data/genus.py). The seed reads them with ast.literal_eval and executes nothing. Two names are respelled to match the Canonn codex: Bark Mound -> Bark Mounds, Radicoida Unicus -> Radicoida Unica.

*** cr_value IS THE BASE SALE PRICE, NOT WHAT A FIRST LOG PAYS. *** Being the first to log a species on a body multiplies it by five, and nothing here knows whether anyone has.';

COMMENT ON COLUMN exobio_species.species_key IS 'The game''s codex token for the species, e.g. ''$Codex_Ent_Stratum_07_Name;''. THE KEY: the game names the species, so nothing is allocated. The journal''s ScanOrganic.Species carries the same token.';
COMMENT ON COLUMN exobio_species.genus_key IS 'The game''s codex token for the genus, e.g. ''$Codex_Ent_Stratum_Genus_Name;'' -- the token Spansh''s genuses list and the journal''s SAASignalsFound.Genuses carry. A Horizons organism with no genus has its own species token here.';
COMMENT ON COLUMN exobio_species.species IS 'English species name, spelled as the Canonn codex spells it (english_name before '' - ''), which is what etl/exobio_odds matches on. Unique.';
COMMENT ON COLUMN exobio_species.genus IS 'English genus name, e.g. ''Stratum''. For a Horizons organism with no genus entry upstream it is the species name.';
COMMENT ON COLUMN exobio_species.cr_value IS 'Vista Genomics base value in credits for a complete three-sample analysis. NOT the first-log payout, which is five times this, and not adjusted for any later price change Frontier makes -- correct the parquet by hand when one happens.';
COMMENT ON COLUMN exobio_species.colony_m IS 'Minimum distance in metres between samples of this genus, as EDMC-ExploData records it. NULL where the genus has no entry upstream.';
COMMENT ON COLUMN exobio_species.bodies_codexed IS 'DERIVED on every load: distinct (system, body) pairs in staging.canonn_codex_event reporting this species. A count of crowd-sourced sightings, so it measures where players went and is NEVER a galaxy census; 0 means no Canonn report, not that the species is absent.';

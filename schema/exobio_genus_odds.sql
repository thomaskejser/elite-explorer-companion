CREATE TABLE IF NOT EXISTS exobio_genus_odds (
    atmosphere     VARCHAR NOT NULL,
    body_type      VARCHAR NOT NULL,
    temp_band      INTEGER NOT NULL,
    star           VARCHAR NOT NULL,
    genus          VARCHAR NOT NULL,
    genus_key      VARCHAR NOT NULL,
    bodies         BIGINT  NOT NULL,
    share          DOUBLE  NOT NULL,
    cr_genus       BIGINT  NOT NULL,
    PRIMARY KEY (atmosphere, body_type, temp_band, star, genus)
);

COMMENT ON TABLE exobio_genus_odds IS
'DERIVED PREDICTION: which exobiology GENERA a landable thin-atmosphere planet carries, by the same cell as main.exobio_odds -- atmosphere, body type, a 20 K temperature band and the arrival star -- one row per genus ever sighted in the cell. Built by etl/exobio_genus_odds/refresh.py from transform.exobio_body (which etl/exobio_odds/refresh.py builds), staging.canonn_codex_event and main.exobio_species. Read by the overlay to show each genus a body may hold, with its chance and its value.

KEY. (atmosphere, body_type, temp_band, star, genus). Each cell also exists with star = ''*'', over every arrival star: a reader takes the star''s own rows when main.exobio_odds.codexed_bodies for that cell is at least 20 and the ''*'' rows otherwise, the rule the overlay uses for cr_species.

*** share IS AMONG BODIES WITH BIOLOGY, NOT AMONG ALL BODIES. *** It is the share of the cell''s codexed bodies (main.exobio_odds.codexed_bodies) on which Canonn has a sighting of this genus. The chance that a body whose biology is not yet known carries the genus is p_bio * share, and p_bio is low by about a third (see main.exobio_odds). Shares of different genera do not sum to 1: a body carries several.

*** IT IS A SIGHTING RATE, NOT A CENSUS. *** Canonn records what commanders reported, and commanders log the valuable genera more often than the cheap ones, so a cheap genus is under-counted. Rank by it; do not quote it as how common a genus is.';

COMMENT ON COLUMN exobio_genus_odds.atmosphere IS 'Spansh atmosphere_type, as in main.exobio_odds. Key part.';
COMMENT ON COLUMN exobio_genus_odds.body_type IS 'Spansh sub_type, as in main.exobio_odds. Key part.';
COMMENT ON COLUMN exobio_genus_odds.temp_band IS 'Temperature cell, kelvin, as in main.exobio_odds. Key part.';
COMMENT ON COLUMN exobio_genus_odds.star IS 'Arrival-star code, or ''*'' for the cell over every star. Key part.';
COMMENT ON COLUMN exobio_genus_odds.genus IS 'main.exobio_species.genus: the English genus name the journal''s SAASignalsFound Genus_Localised also gives (''Bacterium'', ''Brain Tree''). Key part.';
COMMENT ON COLUMN exobio_genus_odds.genus_key IS 'main.exobio_species.genus_key: the game''s codex token for the genus, e.g. ''$Codex_Ent_Bacterial_Genus_Name;'', as SAASignalsFound.Genuses and Spansh''s genuses list carry it.';
COMMENT ON COLUMN exobio_genus_odds.bodies IS 'Codexed bodies in the cell with a Canonn sighting of a species of this genus.';
COMMENT ON COLUMN exobio_genus_odds.share IS 'bodies / main.exobio_odds.codexed_bodies for the cell, 4 dp: the share of bodies WITH BIOLOGY carrying this genus. Not a chance for a body whose biology is unknown; multiply by p_bio for that.';
COMMENT ON COLUMN exobio_genus_odds.cr_genus IS 'Mean base value (main.exobio_species.cr_value) of this genus''s species as sighted in the cell, credits, rounded: what one logged species of the genus is likely worth here. Base price, not the first-log bonus.';

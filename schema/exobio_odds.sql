CREATE TABLE IF NOT EXISTS exobio_odds (
    atmosphere     VARCHAR NOT NULL,
    body_type      VARCHAR NOT NULL,
    temp_band      INTEGER NOT NULL,
    star           VARCHAR NOT NULL,
    bodies         BIGINT  NOT NULL,
    p_bio          DOUBLE  NOT NULL,
    signals_bio    DOUBLE,
    codexed_bodies BIGINT  NOT NULL,
    cr_species     BIGINT,
    cr_bio         BIGINT,
    likely_species VARCHAR,
    PRIMARY KEY (atmosphere, body_type, temp_band, star)
);

COMMENT ON TABLE exobio_odds IS
'DERIVED PREDICTION: how likely a landable thin-atmosphere planet is to carry biology, and what that biology is worth, by the four things that decide it -- atmosphere, body type, a 20 K temperature band and the system''s arrival star. Built by etl/exobio_odds/refresh.py from transform.exobio_body, staging.canonn_codex_event and main.exobio_species. Read by main.system_exobio and by the overlay to value a body it has just scanned.

KEY. (atmosphere, body_type, temp_band, star). Each cell also exists with star = ''*'', fitted over every arrival star: a reader takes the star''s own row when its bodies is at least 200 and the ''*'' row otherwise.

HOW IT IS FITTED.
  p_bio and signals_bio: over Odyssey-era landable bodies (reported on or after 2021-05-19), the share reporting a biology signal and the mean signal count where there is one.
  cr_species and likely_species: over the bodies in the cell with a Canonn species sighting, the mean base value of a sighted species and the commonest three carried by at least 5% of them.
  cr_bio = signals_bio * cr_species, the expected base value of a body that has biology.

*** p_bio IS LOW BY ABOUT A THIRD, AND ONLY ITS ORDER IS TRUSTWORTHY. *** Many scanners never send the biology signal count, so a body reporting none is counted as barren when it may not be. Out of sample, 31,977 pre-Odyssey bodies rescanned after the 2026-07-11 catalogue had biology 12% / 53% / 87% / 95% of the time in the cells predicting 7% / 32% / 54% / 67%: the ranking held, the level did not.
*** cr_species IS A BASE VALUE, NOT A FIRST-LOG PAYOUT *** -- see main.exobio_species.cr_value.
*** NOT A CENSUS. *** Every count is of what players reported, and Canonn sightings follow where players go.';

COMMENT ON COLUMN exobio_odds.atmosphere IS 'Spansh atmosphere_type, e.g. ''Thin Ammonia''. The journal''s Atmosphere field spells it ''thin ammonia atmosphere''. Key part.';
COMMENT ON COLUMN exobio_odds.body_type IS 'Spansh sub_type: High metal content world, Rocky body, Icy body, Rocky Ice world or Metal-rich body. Key part.';
COMMENT ON COLUMN exobio_odds.temp_band IS 'Surface temperature cell in kelvin: floor(temp / 20) * 20, clamped to 100..440, so 160 means 160-180 K and 440 means 440 K and above. Key part.';
COMMENT ON COLUMN exobio_odds.star IS 'main.body.code of the system''s ARRIVAL star (''K'', ''DA'', ''M_RedGiant'', ''?'' where unknown), or ''*'' for the cell over every star. The arrival star is not necessarily the one the body orbits. Key part.';
COMMENT ON COLUMN exobio_odds.bodies IS 'Odyssey-era landable bodies p_bio is fitted on. Below 200 a reader should use the ''*'' row.';
COMMENT ON COLUMN exobio_odds.p_bio IS 'Share of those bodies reporting biology, 4 dp. LOW BY ABOUT A THIRD -- see the table comment; rank by it, do not quote it as a probability.';
COMMENT ON COLUMN exobio_odds.signals_bio IS 'Mean biology signal count among those reporting one, 3 dp: how many species a body with biology carries. NULL where none reported one.';
COMMENT ON COLUMN exobio_odds.codexed_bodies IS 'Bodies in the cell with at least one Canonn species sighting: what cr_species and likely_species stand on. 0 leaves both NULL.';
COMMENT ON COLUMN exobio_odds.cr_species IS 'Mean main.exobio_species.cr_value over the (body, species) sightings in the cell, credits, rounded. NULL with no sighting.';
COMMENT ON COLUMN exobio_odds.cr_bio IS 'signals_bio * cr_species, credits, rounded: the expected base value of a body in this cell that has biology. Multiply by p_bio for a body whose biology is unknown.';
COMMENT ON COLUMN exobio_odds.likely_species IS 'Up to three species most often sighted in the cell, each carried by at least 5% of codexed_bodies and shown with that share, e.g. ''Stratum Tectonicas 61%, Bacterium Aurasus 40%''. Display text, not a key.';

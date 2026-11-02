CREATE TABLE IF NOT EXISTS system_exobio (
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

COMMENT ON TABLE system_exobio IS
'DERIVED PREDICTION: systems whose thin-atmosphere planets probably carry biology nobody has logged, with the expected base value of logging it. One row per system worth at least 10,000,000 credits. Built by etl/system_exobio/refresh.py from transform.exobio_body and main.exobio_odds; read by the overlay''s exobiology panel.

WHICH BODIES COUNT. Three statuses from transform.exobio_body, none of which Canonn reports a sighting on:
  unmapped       -- a biology signal count is reported and the genera are not: seen from orbit and never surface-mapped. Valued as bio_signals * cr_species.
  pre_odyssey    -- last reported before Odyssey (2021-05-19), when the body could be neither landed on nor checked for biology. Valued as p_bio * cr_bio.
  stale_landable -- reported since, but still carrying a pre-Odyssey scan. Valued as pre_odyssey.
Each body takes main.exobio_odds for its own arrival star where that cell has 200 fitted bodies (20 codexed for the species columns) and the ''*'' cell otherwise.

*** THIS TABLE DELETES. *** A row is a prediction, so once its bodies are mapped or codexed, or the system falls below the floor, the row is false rather than stale; the loader deletes rows the transform no longer produces and says how many.
*** NOT A FIRST-FOOTFALL FLAG. *** No source records footfall or first logs. Pre-Odyssey bodies are almost untouched (0.07% carry a Canonn sighting), unmapped bodies less so (5.6%), and a commander who uploads nothing is invisible to both.
*** cr_expected IS LOW. *** exobio_odds.p_bio understates biology by about a third, and the value is the BASE price, before the five-fold first-log bonus.';

COMMENT ON COLUMN system_exobio.system_id IS 'The game''s id64 -- main.system_known.system_id and the journal''s SystemAddress. THE KEY.';
COMMENT ON COLUMN system_exobio.system IS 'Full system name, composed from main.system_known and main.sector with the sector_id = 0 rule. Display and lookup only; not unique across the galaxy, so match on system_id where there is one.';
COMMENT ON COLUMN system_exobio.x IS 'Galactic x, ly, from main.system_known.';
COMMENT ON COLUMN system_exobio.y IS 'Galactic y, ly.';
COMMENT ON COLUMN system_exobio.z IS 'Galactic z, ly.';
COMMENT ON COLUMN system_exobio.candidate_bodies IS 'Thin-atmosphere landable bodies valued here: unmapped, pre_odyssey or stale_landable.';
COMMENT ON COLUMN system_exobio.unmapped_bodies IS 'Of candidate_bodies, those with a reported biology signal -- certain biology, unknown species.';
COMMENT ON COLUMN system_exobio.worked_bodies IS 'Bodies in the system that are already mapped or carry a Canonn sighting. Above 0 means somebody has done exobiology here, so its other bodies may have been visited too.';
COMMENT ON COLUMN system_exobio.cr_expected IS 'Sum over candidate_bodies of the expected base value, credits, rounded. At least 10,000,000. Low: see the table comment.';
COMMENT ON COLUMN system_exobio.best_body IS 'Full Spansh name of the candidate body with the highest expected value, system prefix included.';
COMMENT ON COLUMN system_exobio.best_cr IS 'That body''s expected base value, credits, rounded.';
COMMENT ON COLUMN system_exobio.best_species IS 'main.exobio_odds.likely_species for that body''s cell: what has been found on bodies like it, not on it.';
COMMENT ON COLUMN system_exobio.last_reported IS 'The latest Spansh report on any candidate body. Before 2021-05-19 means no candidate has been reported since Odyssey.';

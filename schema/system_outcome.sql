-- system_outcome: the prediction for each predicted system this commander visited, frozen
-- at the first visit, and what the commander's own scans found there.
-- Database: elite_mapping_current.duckdb (app state). Written only by the overlay.
CREATE TABLE IF NOT EXISTS system_outcome (
    system            VARCHAR NOT NULL PRIMARY KEY,
    system_id         BIGINT,
    sector            VARCHAR,
    first_visited_utc TIMESTAMPTZ NOT NULL,
    is_catalog        BOOLEAN NOT NULL,
    mass_code         VARCHAR,
    p_bh              DOUBLE,
    p_wr              DOUBLE,
    p_herbig          DOUBLE,
    p_otype           DOUBLE,
    p_neutron         DOUBLE,
    p_wd              DOUBLE,
    found_bh          BOOLEAN NOT NULL,
    found_wr          BOOLEAN NOT NULL,
    found_herbig      BOOLEAN NOT NULL,
    found_otype       BOOLEAN NOT NULL,
    found_neutron     BOOLEAN NOT NULL,
    found_wd          BOOLEAN NOT NULL,
    scanned_stars     VARCHAR[] NOT NULL,
    all_bodies_found  BOOLEAN NOT NULL,
    updated_utc       TIMESTAMPTZ NOT NULL
);

COMMENT ON TABLE system_outcome IS
'APP STATE: the out-of-sample test of the model, one row per PREDICTED system this commander visited. The p_ columns are copied from the overlay''s system_predicted at the first arrival and never changed afterwards, so they are the prediction as it stood BEFORE the visit; the found_ columns accumulate from the journal''s Scan events for stars in that system. A system not in system_predicted when visited gets no row: there is no prediction to test. NEVER deleted. *** found_ IS ONLY AS COMPLETE AS THE SCANNING. *** A kind not found in a system whose all_bodies_found is FALSE may simply not have been scanned; compare predicted against found over all_bodies_found = TRUE rows for an unbiased rate. Read by the overlay''s Settings tab.';

COMMENT ON COLUMN system_outcome.system IS 'The full system name as the journal spells it, and the natural key.';
COMMENT ON COLUMN system_outcome.system_id IS 'The game''s id64, from system_predicted when it had one: NULL for a boxel-predicted system, which no feed had reported.';
COMMENT ON COLUMN system_outcome.sector IS 'The procedural sector, from system_predicted.';
COMMENT ON COLUMN system_outcome.first_visited_utc IS 'When the commander first arrived, from the arrival event''s timestamp. The prediction is as of this moment.';
COMMENT ON COLUMN system_outcome.is_catalog IS 'system_predicted.is_catalog at the visit: TRUE for a catalogued system not yet scanned, FALSE for a boxel prediction.';
COMMENT ON COLUMN system_outcome.mass_code IS 'The boxel mass code, the model''s strongest predictor.';
COMMENT ON COLUMN system_outcome.p_bh IS 'P(system contains a black hole) as predicted before the visit. A ranking-grade rate, biased upward; see system_predicted.p_bh.';
COMMENT ON COLUMN system_outcome.p_wr IS 'P(system contains a Wolf-Rayet) as predicted before the visit.';
COMMENT ON COLUMN system_outcome.p_herbig IS 'P(system contains a Herbig Ae/Be) as predicted before the visit.';
COMMENT ON COLUMN system_outcome.p_otype IS 'P(system contains an O-type star) as predicted before the visit.';
COMMENT ON COLUMN system_outcome.p_neutron IS 'P(system contains a neutron star) as predicted before the visit.';
COMMENT ON COLUMN system_outcome.p_wd IS 'P(system contains a white dwarf) as predicted before the visit.';
COMMENT ON COLUMN system_outcome.found_bh IS 'TRUE once a scanned star in the system had a black-hole StarType (H, SupermassiveBlackHole). Only ever turns TRUE.';
COMMENT ON COLUMN system_outcome.found_wr IS 'TRUE once a scanned star was a Wolf-Rayet (W, WN, WNC, WC, WO).';
COMMENT ON COLUMN system_outcome.found_herbig IS 'TRUE once a scanned star was a Herbig Ae/Be (AeBe).';
COMMENT ON COLUMN system_outcome.found_otype IS 'TRUE once a scanned star was O-type.';
COMMENT ON COLUMN system_outcome.found_neutron IS 'TRUE once a scanned star was a neutron star (N).';
COMMENT ON COLUMN system_outcome.found_wd IS 'TRUE once a scanned star was a white dwarf (D and its subclasses).';
COMMENT ON COLUMN system_outcome.scanned_stars IS 'Body names of the stars the journal reported scanning here, distinct; its length is how many stars the outcome rests on.';
COMMENT ON COLUMN system_outcome.all_bodies_found IS 'TRUE once the journal reported FSSAllBodiesFound for the system: every body was discovered, so a kind still not found is genuinely absent.';
COMMENT ON COLUMN system_outcome.updated_utc IS 'When this row last changed.';

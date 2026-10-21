CREATE TABLE IF NOT EXISTS prediction_outcome (
    system           VARCHAR NOT NULL,
    is_catalog       BOOLEAN NOT NULL,
    system_id        BIGINT  NOT NULL,
    sector           VARCHAR,
    mass_code        VARCHAR NOT NULL,
    x DOUBLE, y DOUBLE, z DOUBLE,
    p_bh DOUBLE, p_wr DOUBLE, p_neutron DOUBLE, p_wd DOUBLE, p_herbig DOUBLE,
    p_otype DOUBLE, p_supergiant DOUBLE,
    exp_bodies       DOUBLE,
    predicted_in     VARCHAR NOT NULL,
    recorded_utc     TIMESTAMPTZ NOT NULL,
    first_seen       TIMESTAMPTZ,
    revealed_by      VARCHAR NOT NULL,
    primary_code     VARCHAR,
    surveyed_bodies  INTEGER NOT NULL,
    catalogue_bodies INTEGER NOT NULL,
    found_bh BOOLEAN NOT NULL, found_wr BOOLEAN NOT NULL, found_neutron BOOLEAN NOT NULL,
    found_wd BOOLEAN NOT NULL, found_herbig BOOLEAN NOT NULL, found_otype BOOLEAN NOT NULL,
    found_supergiant BOOLEAN NOT NULL,
    UNIQUE (system, is_catalog)
);

COMMENT ON TABLE prediction_outcome IS
'OUT-OF-SAMPLE TEST: one row per prediction whose system the galaxy has since revealed, holding the prediction as it stood before the reveal beside what turned up. Built by etl/prediction_outcome/refresh.py, which must run AFTER system_known and system_body load and BEFORE system_predicted refreshes, because that refresh deletes every prediction this table exists to catch.

RESOLVED MEANS: a catalogued prediction (is_catalog TRUE) whose system now has a system_body row, or a boxel prediction (is_catalog FALSE) whose name now resolves to a main.system_known row. The prediction columns (p_*, exp_bodies, mass_code, x/y/z) are copied once, from the latest source that still held the prediction, and NEVER updated; the actual columns are recomputed on every run, so found_* grows as more bodies arrive.

NEVER DELETED: a recorded outcome stays even after its system leaves every snapshot.

*** NOT A RANDOM SAMPLE. *** Commanders scan systems that already look interesting, so the resolved set is enriched for exotic stars and an observed rate ABOVE the predicted one is the expected direction of that bias. Rank (does a higher p mean a higher hit rate) is the test this supports; calibration is not.

*** FOUND IS A LOWER BOUND. *** No source carries a fully-scanned flag, so found_* FALSE means "not reported yet". revealed_by = ''catalogue'' rows were revealed by a catalogue hit that contains its target by construction: EXCLUDE them from any hit rate, or found is inflated. Score over revealed_by = ''survey''.';

COMMENT ON COLUMN prediction_outcome.system IS 'system_predicted.system at prediction time. With is_catalog, the natural key: a boxel prediction that resolves is predicted again as a catalogued system under the same name, and both outcomes are kept.';
COMMENT ON COLUMN prediction_outcome.is_catalog IS 'TRUE: the prediction was for a known system with no body data. FALSE: for a boxel-index gap no dump reported.';
COMMENT ON COLUMN prediction_outcome.system_id IS 'The game''s id64 (main.system_known.system_id). For a boxel prediction, resolved by parsing the predicted name back into sector, cube, mass code, sub-cube and index and matching system_known on them; a prediction matching more than one system is not recorded.';
COMMENT ON COLUMN prediction_outcome.sector IS 'Procedural sector name, from the prediction.';
COMMENT ON COLUMN prediction_outcome.mass_code IS 'Boxel mass code, from the prediction. Group by it before averaging any p_: see system_predicted.';
COMMENT ON COLUMN prediction_outcome.x IS 'Predicted position: exact for a catalogued prediction, the boxel mean for a boxel one.';
COMMENT ON COLUMN prediction_outcome.y IS 'See x.';
COMMENT ON COLUMN prediction_outcome.z IS 'See x.';
COMMENT ON COLUMN prediction_outcome.p_bh IS 'P(black hole) as predicted before the reveal. Frozen.';
COMMENT ON COLUMN prediction_outcome.p_wr IS 'P(Wolf-Rayet) as predicted before the reveal. Frozen.';
COMMENT ON COLUMN prediction_outcome.p_neutron IS 'P(neutron star) as predicted before the reveal. Frozen.';
COMMENT ON COLUMN prediction_outcome.p_wd IS 'P(white dwarf) as predicted before the reveal. Frozen.';
COMMENT ON COLUMN prediction_outcome.p_herbig IS 'P(Herbig Ae/Be) as predicted before the reveal. Frozen.';
COMMENT ON COLUMN prediction_outcome.p_otype IS 'P(O-type star) as predicted before the reveal. Frozen.';
COMMENT ON COLUMN prediction_outcome.p_supergiant IS 'P(supergiant) as predicted before the reveal. Frozen.';
COMMENT ON COLUMN prediction_outcome.exp_bodies IS 'Expected body count as predicted before the reveal. Frozen.';
COMMENT ON COLUMN prediction_outcome.predicted_in IS 'Where the frozen prediction was read: main.system_predicted, or a staging.pred_snapshot_<date> taken before an earlier refresh.';
COMMENT ON COLUMN prediction_outcome.recorded_utc IS 'When this loader first recorded the outcome. The reveal happened at or before it.';
COMMENT ON COLUMN prediction_outcome.first_seen IS 'main.system_known.first_seen: when the system entered system_known.';
COMMENT ON COLUMN prediction_outcome.revealed_by IS '''survey'': at least one system_body row from a survey feed (spansh, edsm, edastro). ''catalogue'': only catalogue hits (edastro_rare, edastro_neutron, canonn_codex), which contain their target by construction. ''known'': a boxel prediction now in system_known with no body rows, so only primary_code is an actual.';
COMMENT ON COLUMN prediction_outcome.primary_code IS 'body.code of system_known.primary_star_body_id: the primary star''s class, NULL when no feed gives it.';
COMMENT ON COLUMN prediction_outcome.surveyed_bodies IS 'system_body rows from survey feeds. How much the found_ columns rest on.';
COMMENT ON COLUMN prediction_outcome.catalogue_bodies IS 'system_body rows from catalogue feeds.';
COMMENT ON COLUMN prediction_outcome.found_bh IS 'TRUE when the primary or any body is a black hole (H, SupermassiveBlackHole). A lower bound: see the table comment.';
COMMENT ON COLUMN prediction_outcome.found_wr IS 'TRUE when the primary or any body is a Wolf-Rayet (W, WN, WNC, WC, WO).';
COMMENT ON COLUMN prediction_outcome.found_neutron IS 'TRUE when the primary or any body is a neutron star (N).';
COMMENT ON COLUMN prediction_outcome.found_wd IS 'TRUE when the primary or any body is a white dwarf (D and its subclasses).';
COMMENT ON COLUMN prediction_outcome.found_herbig IS 'TRUE when the primary or any body is a Herbig Ae/Be (AeBe).';
COMMENT ON COLUMN prediction_outcome.found_otype IS 'TRUE when the primary or any body is O-type.';
COMMENT ON COLUMN prediction_outcome.found_supergiant IS 'TRUE when the primary or any body is a supergiant (A/B blue-white, F/G white, M red).';

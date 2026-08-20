-- system_predicted: per-system target probabilities. Load order tier 3.
-- NO foreign key to system_known ON PURPOSE: the boxel-predicted rows (is_catalog
-- FALSE) describe systems that are in no dump and therefore have no system_known
-- parent. PREDICTS -- it is the one table allowed to DELETE (see ETL.md 3).
-- is_catalog is LAST because it replaced a VARCHAR `source` column via ALTER TABLE
-- ADD COLUMN, which can only append; moving it up would make a fresh database
-- disagree with a migrated one under DESCRIBE.
CREATE TABLE IF NOT EXISTS system_predicted (
    system_predicted_id BIGINT  NOT NULL PRIMARY KEY,
    system_name         VARCHAR NOT NULL,
    system_id64         BIGINT,
    mass_code           VARCHAR NOT NULL,
    sector              VARCHAR,
    boxel               VARCHAR,
    x DOUBLE, y DOUBLE, z DOUBLE,
    plane_r DOUBLE, r_sgra DOUBLE, dist_sol DOUBLE,
    p_bh DOUBLE, p_wr DOUBLE,
    p_bh_model DOUBLE, p_wr_model DOUBLE,
    p_hr DOUBLE,
    p_neutron DOUBLE, p_wd DOUBLE, p_herbig DOUBLE,
    p_otype DOUBLE, p_supergiant DOUBLE,
    exp_bodies DOUBLE, exp_scan_value_cr DOUBLE,
    is_catalog BOOLEAN NOT NULL,
    UNIQUE (system_name)
);

-- --------------------------------------------------------------------------
-- COMMENTS. Kept in this file, beside the DDL they describe, so a schema change
-- and its documentation cannot drift apart. Re-applied by the builder after every
-- merge via common.db.apply_comment_file(), because a migration is the one thing
-- that silently drops a comment.
-- --------------------------------------------------------------------------

-- Canonical COMMENT for `system_predicted`. Edit here, nowhere else: the builder
-- re-asserts this file after every merge (ETL.md -- a migration is the one thing that
-- silently drops comments).
COMMENT ON TABLE system_predicted IS
'PREDICTION TABLE: one row per system we can say something about WITHOUT having scanned
it, with a probability per target. Built by etl/build_system_predicted.py, a DERIVED
table -- no input/ parquet, no loader.

*** THESE ARE PREDICTIONS, NOT OBSERVATIONS. *** Nothing here has been confirmed in
game. A row is a place worth flying to, never evidence a thing exists.

TWO POPULATIONS, VERY DIFFERENT RELIABILITY -- always check `is_catalog`:
  is_catalog TRUE  (2,206,895)  REAL catalogued systems with EXACT coordinates that
                                nobody has detail-scanned. Trustworthy targets.
  is_catalog FALSE (50,212)     BOXEL-PREDICTED: Stellar-Forge-implied systems in NO
                                dump, enumerated from internal boxel index gaps.
                                BOXEL-CENTROID coordinates ONLY, so you may arrive and
                                find nothing at the exact spot. RECOMMENDATIONS.md
                                R2/R3: this layer is thin and heavily CORE-BIASED and is
                                NOT a usable basis for fringe estimates. A lower bound.

*** NEVER average a probability across the two without also grouping by mass_code. ***
The catalogued pool is 90.3% mass code e (p_bh ~0.04); the boxel-predicted pool has NO e
at all and is 45.2% h (p_bh ~0.46). The resulting gap in mean p_bh (0.084 vs 0.425) is
pure COMPOSITION, not target quality -- within any single mass code the two agree closely
(h: 0.4473 catalogued vs 0.4585 boxel-predicted). This is a Simpson''s-paradox trap.

THIS TABLE DELETES. Unlike every other merge target in etl/, a row here is REMOVED once
its system stops qualifying -- a prediction that has been invalidated is not a retired
key, it is a wrong row, and leaving it would keep offering a target that no longer
exists. Nothing has a foreign key into this table, so ETL.md''s merge-never-drop rule
(which exists to protect keys others point at) does not apply.

SCOPE: mass codes e/f/g/h only. That is not laziness -- it is where these targets are
predictable at all. R1 gates black holes and Wolf-Rayets to e/f/g/h (0.000% in a,b,c,d
across 72,261,736 scanned systems, confidence A), and edastro_boxel_stats, the only
helium source in the project, covers e/f/g/h ONLY with no d and below. An a/b/c/d row
would be p_bh=0, p_wr=0, p_hr=NULL and would carry no information.

TWO FAMILIES OF PROBABILITY, deliberately in separate columns -- do not average them:
  p_*        EMPIRICAL rate, measured at build time over SCANNED systems by
             (mass_code, plane_r band), the same cut R1/R2 are published in. Present for
             BOTH sources. Pure SQL, reproducible, no model.
  p_*_model  The 03c gradient-boosted score, LEFT JOINed from bhwr_candidates. Present
             only where that legacy table happens to hold the system; NULL for every
             is_catalog=FALSE row (never scored) and for catalogued systems it lacks. Its source table warns RANKINGS are the trustworthy output and
             absolute levels are biased upward; app/candidates.parquet carries the
             flight-calibrated version.

ALREADY-FOUND SYSTEMS ARE EXCLUDED, NOT FLAGGED. The pool is system_known MINUS
system_body: a system holding even ONE body row is out. That includes bodies contributed
by the EDAstro FULL catalogues (system_body.source = ''edastro_rare'' / ''edastro_neutron'').
If a black hole, Wolf-Rayet or neutron there is already catalogued then a commander has
been and scanned it, so the system is EXPLORED and is not something to predict. There
are deliberately no edastro_bh / edastro_wr flag columns: those rows are gone, not
marked, so you cannot forget to filter them.

NOT INDEPENDENT. p_bh and p_wr compete for the same primary star and are normalised
against each other upstream; p_hr does NOT compete with either -- a system can hold a
black hole and a helium-rich gas giant at once, they are different bodies. Do not
multiply these together as if independent, and do not sum them into a "chance of
anything".';

COMMENT ON COLUMN system_predicted.system_predicted_id IS
'BIGINT PRIMARY KEY surrogate, allocated max+1. NOT a game id and NOT stable across a
rebuild from scratch -- join on system_name, which is the NATURAL key. Existing ids are
never renumbered and retired ids never reused (ETL.md).';

COMMENT ON COLUMN system_predicted.system_name IS
'Full procedural system name, e.g. ''Byoomiae LM-W f1-4107''. THE NATURAL KEY, and unique
across the table (enforced by a UNIQUE constraint) -- merges match on this, never on
system_predicted_id. For is_catalog=FALSE rows it is RECONSTRUCTED as boxel_key||index
and is what the system WOULD be called; verified that none of them collides with a name
already known to the catalogue.';

COMMENT ON COLUMN system_predicted.system_id64 IS
'The game''s 64-bit system id, resolved through staging.sys_bridge. Present for
is_catalog=TRUE rows, NULL for is_catalog=FALSE -- a system in no dump has no id64,
because id64 comes from the dumps. Fall back to system_name, which is always present and
is the natural key.';

COMMENT ON COLUMN system_predicted.is_catalog IS
'TRUE = the system is CATALOGUED: it appears in the dumps with EXACT coordinates, and
simply has not been detail-scanned. FALSE = BOXEL-PREDICTED: it appears in no dump at all
and its existence is inferred from a gap in the Stellar Forge''s boxel index sequence, so
its coordinates are the BOXEL CENTROID -- a boxel is up to 1280 ly across, so you can fly
to the coordinates and find nothing at that exact spot. The FALSE layer is also thin and
heavily core-biased (RECOMMENDATIONS.md R2/R3) and is a lower bound, not a census.
*** Always filter or group by this. *** Mixing the two silently mixes a trustworthy
target list with an approximate one. And never average a probability across it without
also grouping by mass_code: the TRUE pool is 89.4% mass code e while the FALSE pool has
no e at all, so a raw comparison measures composition, not target quality.';

COMMENT ON COLUMN system_predicted.mass_code IS
'Procedural mass code, ''e''..''h''. Parsed from the NAME, so it is known WITHOUT scanning --
that is what makes this whole table possible. A hard Stellar Forge gate on star type
(R1) and the strongest single driver of scan value (R7, 25x spread). Never a,b,c,d here:
those are out of scope, not missing.';

COMMENT ON COLUMN system_predicted.sector IS
'Procedural sector name, e.g. ''Byoomiae''. Derived by stripping the boxel suffix from the
name for is_catalog=TRUE rows, carried from theorised_system for is_catalog=FALSE rows.
Use it to join the sector-level rankings in sector_unscanned / explore_sectors.';

COMMENT ON COLUMN system_predicted.boxel IS
'Boxel key parsed from the name, in EDAstro''s form -- ''Eor Bru FW-W f#1'' where a sub-cube
exists, plain ''Flyiedgou ZE-A g'' where it does not. Parsed with the SAME expression as
scripts/build_candidates.py so the two agree; it is the join key to
edastro_boxel_stats and therefore the only route to p_hr.';

COMMENT ON COLUMN system_predicted.x IS
'Galactic x, light years, Sol = 0. EXACT where is_catalog; BOXEL-CENTROID where NOT
is_catalog, and the true system may sit anywhere inside a boxel up to 1280 ly across.';

COMMENT ON COLUMN system_predicted.y IS
'Galactic y (height above the galactic plane), light years, Sol = 0. EXACT where
is_catalog; BOXEL-CENTROID where NOT is_catalog.';

COMMENT ON COLUMN system_predicted.z IS
'Galactic z, light years, Sol = 0. EXACT where is_catalog; BOXEL-CENTROID where NOT
is_catalog.';

COMMENT ON COLUMN system_predicted.plane_r IS
'Galactocentric DISK radius in light years (distance from the galactic axis, ignoring
height). Sol ~25,900; rim ~50,000. This is the band variable the empirical p_* rates are
fitted in, using R2''s bands (0-10k / 10-20k / 20-30k / 30k+).';

COMMENT ON COLUMN system_predicted.r_sgra IS
'Distance from Sagittarius A* in light years. Gates p_hr: ZERO helium-rich gas giants in
690,795 fully-scanned systems within 5,500 ly of Sgr A*, so p_hr is forced to 0 inside
that radius.';

COMMENT ON COLUMN system_predicted.dist_sol IS
'Straight-line distance from Sol in light years, sqrt(x^2+y^2+z^2). Trip-planning
convenience only -- it is NOT a predictor: R7 found scan value varies only 0.84-1.15x
across distance bands, unlike mass code.';

COMMENT ON COLUMN system_predicted.p_bh IS
'P(system contains a black hole), EMPIRICAL rate for this (mass_code, plane_r band)
measured over scanned systems with n_stars>0. Present for BOTH sources. Rate, not
certainty: p_bh=0.45 means 45% of scanned systems in this cell held one. Biased UPWARD
because explorers preferentially scan the bright massive primary, so scanned systems
over-represent black holes within a cell -- treat as a RANKING. Competes with p_wr for
the same primary star; do not add them.';

COMMENT ON COLUMN system_predicted.p_wr IS
'P(system contains a Wolf-Rayet star), EMPIRICAL rate for this (mass_code, plane_r band)
over scanned systems. Effectively zero outside mass code h (R1). Competes with p_bh for
the same primary star -- one star cannot be both, so never add or multiply them. Same
upward bias as p_bh.';

COMMENT ON COLUMN system_predicted.p_bh_model IS
'P(black hole) from the 03c gradient-boosted model (bhwr_candidates), trained on scanned
e/f/g/h with spatial GroupKFold CV. NULL for is_catalog=FALSE rows -- never scored.
*** RANKINGS are the trustworthy output; the absolute level is biased upward *** and
app/candidates.parquet holds the flight-calibrated version. Kept beside the empirical
p_bh rather than blended into it so the two methods stay separable.';

COMMENT ON COLUMN system_predicted.p_wr_model IS
'P(Wolf-Rayet) from the 03c model (bhwr_candidates). NULL where NOT is_catalog. Same
ranking-not-level caveat as p_bh_model.';

COMMENT ON COLUMN system_predicted.p_hr IS
'P(system contains a HELIUM-RICH GAS GIANT) -- the one PLANET class that is predictable
at all. Earth-likes, ammonia and water worlds show only 1.3-1.9x per-boxel
overdispersion, which vanishes once the arrival star is held fixed (DEAD_ENDS.md);
helium-rich shows 5.4x. Two HARD GATES then a fitted lookup: forced to 0 for mass_code
''h'' (zero hits in 64,315 fully-scanned h systems where the g rate implies ~130), forced
to 0 inside r_sgra 5,500 ly, and otherwise read off EDAstro''s published per-boxel
gas-giant helium fraction -- flat zero below 29%, rising to ~63% by 33.5%.
*** NOT normalised against p_bh/p_wr: *** a system can hold a black hole AND a
helium-rich gas giant, they are different bodies.
*** helium_avg aggregates SCANNED gas giants, so this can only rate a boxel somebody has
already dipped into -- it predicts the REST of a sampled boxel, never a virgin one. ***
0.0 therefore means "gated out or no helium data", not "known absent".';

COMMENT ON COLUMN system_predicted.p_neutron IS
'P(system contains a neutron star), empirical rate for this (mass_code, plane_r band)
from star_agg over scanned systems. Neutrons cluster hard but are common enough that
they are rarely worth routing for on their own; note that g/h neutrons are never the
arrival star, so arriving does not confirm one.';

COMMENT ON COLUMN system_predicted.p_wd IS
'P(system contains a white dwarf of any variant D/DA/DAB/.../DX), empirical rate for this
(mass_code, plane_r band) from star_agg over scanned systems.';

COMMENT ON COLUMN system_predicted.p_herbig IS
'P(system contains a Herbig Ae/Be star), empirical rate for this (mass_code, plane_r
band) from star_agg. *** The best rim-ward target in the project *** -- R2: the only one
whose rate RISES with galactocentric radius (4.6% in e, ~18% in f/g out past 30 kly),
giving ~2,982 expected finds beyond 30 kly against ~319 black holes.';

COMMENT ON COLUMN system_predicted.p_otype IS
'P(system contains an O-type star), empirical rate for this (mass_code, plane_r band)
from star_agg. Concentrated in g-mass systems, but the richest O-type sectors sit ~55 kly
from Sol on the far side of the core (R4) -- check dist_sol before routing.';

COMMENT ON COLUMN system_predicted.p_supergiant IS
'P(system contains a supergiant of any class), empirical rate for this (mass_code,
plane_r band) from star_agg. The BEST-VALIDATED rare-star prediction in the project
(R5: 2.4x observed-over-expected).';

COMMENT ON COLUMN system_predicted.exp_bodies IS
'Expected number of bodies a FULL scan of this system would reveal, the mean over scanned
systems of the same mass code. Mass code only, not banded by radius, because R7 found
value varies 25x across mass code but only 0.84-1.15x with distance. An expectation over
a wide distribution, NOT a per-system estimate.';

COMMENT ON COLUMN system_predicted.exp_scan_value_cr IS
'Expected BASE exploration value in credits of fully scanning this system -- the mean
over scanned systems of the same mass code, divided by the measured 77.1% scan
completeness so it represents a FULL scan rather than the partial scans our data holds.
*** BASE ONLY: no multiplier. *** First-discovery is x2.6; mapping multipliers (x8.0956
first-mapped, x1.25 efficient, Odyssey bonus) are NOT applied and CANNOT be, because no
source we hold has a DSS/mapped flag. For a first-discovery estimate multiply by 2.6.
Value is realised only on sale to Universal Cartographics. See RECOMMENDATIONS.md R7.';

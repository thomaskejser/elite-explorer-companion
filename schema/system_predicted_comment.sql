-- Canonical COMMENT for `system_predicted`. Edit here, nowhere else: the builder
-- re-asserts this file after every merge (ETL.md -- a migration is the one thing that
-- silently drops comments).
COMMENT ON TABLE system_predicted IS
'PREDICTION TABLE: one row per system we can say something about WITHOUT having scanned
it, with a probability per target. Built by etl/build_system_predicted.py, a DERIVED
table -- no input/ parquet, no loader.

*** THESE ARE PREDICTIONS, NOT OBSERVATIONS. *** Nothing here has been confirmed in
game. A row is a place worth flying to, never evidence a thing exists.

TWO POPULATIONS, VERY DIFFERENT RELIABILITY -- always check `source`:
  catalogued_unscanned (2,255,468)  REAL catalogued systems with EXACT coordinates that
                                    nobody has detail-scanned. Trustworthy targets.
  theorised (57,700)                Stellar-Forge-implied systems in NO dump, enumerated
                                    from internal boxel index gaps. BOXEL-CENTROID
                                    coordinates ONLY, so you may arrive and find nothing
                                    at the exact spot. RECOMMENDATIONS.md R2/R3: this
                                    layer is thin and heavily CORE-BIASED and is NOT a
                                    usable basis for fringe estimates. A lower bound.

SCOPE: mass codes e/f/g/h only. That is not laziness -- it is where these targets are
predictable at all. R1 gates black holes and Wolf-Rayets to e/f/g/h (0.000% in a,b,c,d
across 72,261,736 scanned systems, confidence A), and edastro_boxel_stats, the only
helium source in the project, covers e/f/g/h ONLY with no d and below. An a/b/c/d row
would be p_bh=0, p_wr=0, p_hr=NULL and would carry no information.

TWO FAMILIES OF PROBABILITY, deliberately in separate columns -- do not average them:
  p_*        EMPIRICAL rate, measured at build time over SCANNED systems by
             (mass_code, plane_r band), the same cut R1/R2 are published in. Present for
             BOTH sources. Pure SQL, reproducible, no model.
  p_*_model  The 03c gradient-boosted score, carried from bhwr_candidates. Present for
             catalogued_unscanned ONLY -- theorised systems were never scored, so it is
             NULL there. Its source table warns RANKINGS are the trustworthy output and
             absolute levels are biased upward; app/candidates.parquet carries the
             flight-calibrated version.

ALREADY-FOUND SYSTEMS ARE STILL HERE. edastro_bh / edastro_wr mark systems EDAstro
already catalogues. Their rows are kept because such a system may still be an unscanned
candidate for helium or a neutron, and the probabilities remain honest predictions of
what a fresh scan would show. *** Filter them out before routing a BH/WR trip *** --
42% of the h pool is already catalogued.

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
system_predicted_id. For theorised rows it is RECONSTRUCTED as boxel_key || boxel_index
and is what the system WOULD be called; verified that none of the 57,700 collides with a
name already in sys_feat.';

COMMENT ON COLUMN system_predicted.system_id64 IS
'The game''s 64-bit system id. Present for catalogued_unscanned rows, NULL for theorised
rows -- a system in no dump has no id64, because id64 comes from the dumps. Use it to
join sys_feat / spansh_system; fall back to system_name when it is NULL.';

COMMENT ON COLUMN system_predicted.source IS
'''catalogued_unscanned'' = a REAL catalogued system with EXACT coordinates that nobody has
detail-scanned. ''theorised'' = Stellar-Forge-implied, present in no dump, BOXEL-CENTROID
coordinates only, thin and core-biased (RECOMMENDATIONS.md R2/R3). *** Always filter or
group by this. *** Mixing the two silently mixes a trustworthy target list with a lower
bound whose coordinates are approximate.';

COMMENT ON COLUMN system_predicted.mass_code IS
'Procedural mass code, ''e''..''h''. Parsed from the NAME, so it is known WITHOUT scanning --
that is what makes this whole table possible. A hard Stellar Forge gate on star type
(R1) and the strongest single driver of scan value (R7, 25x spread). Never a,b,c,d here:
those are out of scope, not missing.';

COMMENT ON COLUMN system_predicted.sector IS
'Procedural sector name, e.g. ''Byoomiae''. Derived by stripping the boxel suffix from the
name for catalogued rows, carried from theorised_system for theorised rows. Use it to
join the sector-level rankings in sector_unscanned / explore_sectors.';

COMMENT ON COLUMN system_predicted.boxel IS
'Boxel key parsed from the name, in EDAstro''s form -- ''Eor Bru FW-W f#1'' where a sub-cube
exists, plain ''Flyiedgou ZE-A g'' where it does not. Parsed with the SAME expression as
scripts/build_candidates.py so the two agree; it is the join key to
edastro_boxel_stats and therefore the only route to p_hr.';

COMMENT ON COLUMN system_predicted.x IS
'Galactic x, light years, Sol = 0. EXACT for catalogued_unscanned; BOXEL-CENTROID for
theorised, where the true system may sit anywhere inside a boxel up to 1280 ly across.';

COMMENT ON COLUMN system_predicted.y IS
'Galactic y (height above the galactic plane), light years, Sol = 0. EXACT for
catalogued_unscanned; BOXEL-CENTROID for theorised.';

COMMENT ON COLUMN system_predicted.z IS
'Galactic z, light years, Sol = 0. EXACT for catalogued_unscanned; BOXEL-CENTROID for
theorised.';

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
e/f/g/h with spatial GroupKFold CV. NULL for theorised rows -- they were never scored.
*** RANKINGS are the trustworthy output; the absolute level is biased upward *** and
app/candidates.parquet holds the flight-calibrated version. Kept beside the empirical
p_bh rather than blended into it so the two methods stay separable.';

COMMENT ON COLUMN system_predicted.p_wr_model IS
'P(Wolf-Rayet) from the 03c model (bhwr_candidates). NULL for theorised rows. Same
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

COMMENT ON COLUMN system_predicted.edastro_bh IS
'TRUE if EDAstro''s FULL Black-Holes.csv catalogue already lists this system -- the black
hole is ALREADY FOUND, so p_bh is not an opportunity here. Rows are kept rather than
deleted because the system may still be an unscanned candidate for helium or a neutron.
*** Filter on NOT edastro_bh before routing a black-hole trip: 42% of the h pool is
already catalogued. *** Sourced from the full per-class catalogue, not a 7-day slice.';

COMMENT ON COLUMN system_predicted.edastro_wr IS
'TRUE if EDAstro''s FULL Wolf-Rayet-stars.csv catalogue already lists this system -- the
Wolf-Rayet is ALREADY FOUND. Same treatment and same warning as edastro_bh: filter it out
before routing, do not treat a TRUE row as a prediction target.';

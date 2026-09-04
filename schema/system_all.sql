-- system_all: every system we can name, observed and inferred, in one place.
-- Database: elite_mapping_v2.duckdb (the model).
-- A VIEW, not a table -- nothing here is stored. Load order tier 4: it reads
-- system_known, system_predicted, sector and region, so all four must exist first.
--
-- *** CREATE OR REPLACE VIEW SILENTLY DROPS EVERY COMMENT ON IT. *** Verified, not
-- assumed. That is the same trap a migration sets for a table, which is why the
-- comments live in this file beside the DDL and etl/build_system_all.py re-applies the
-- whole file every run.
CREATE OR REPLACE VIEW system_all AS
-- OBSERVED. One row per system somebody has actually reported.
SELECT k.system_id,
       k.id64,
       -- The full name the game uses. sector_id = 0 is the 'crafted' SENTINEL, and it
       -- is the one case where a system's name stands alone -- 'Sol', not
       -- 'crafted Sol'. See sector.sql: is_crafted is TRUE for 424 real named sectors
       -- too, so the sentinel must be tested by ID and never by that flag.
       CASE WHEN k.sector_id = 0 THEN k.system_in_sector
            ELSE sc.sector || ' ' || k.system_in_sector END AS system,
       CASE WHEN k.sector_id = 0 THEN NULL ELSE sc.sector END AS sector,
       r.region,
       k.mass_code,
       FALSE AS is_predicted,
       k.x, k.y, k.z
FROM system_known k
JOIN sector sc      ON sc.sector_id = k.sector_id
-- LEFT, though system_known.region_id is NOT NULL in all 197,764,363 rows today. A
-- view that quietly loses rows when an assumption lapses is worse than one that shows
-- a NULL region, because the row count is the thing nobody re-checks.
LEFT JOIN region r  ON r.region_id  = k.region_id

UNION ALL

-- INFERRED. Boxel-predicted systems only -- in no dump at all, enumerated from gaps in
-- the Stellar Forge index.
--
-- *** THE CATALOGUED HALF OF system_predicted IS DELIBERATELY EXCLUDED, AND THIS IS
-- THE ONE JUDGEMENT CALL IN THE VIEW. *** Measured: all 2,207,261 is_catalog rows
-- resolve to a system_known row by id64, and all 61,763 boxel rows resolve to none
-- (their system_id64 is NULL outright). So including the catalogued half would list
-- 2.2M systems TWICE, once as observed and once as predicted, and every count over
-- this view would be wrong by that much. They are not lost: they are the same systems,
-- present above with is_predicted = FALSE, which is what they are -- system_predicted's
-- own comment calls them "REAL catalogued systems". is_predicted here means "we
-- inferred that this system exists", not "we have a probability for it".
SELECT NULL::BIGINT AS system_id,
       p.system_id64 AS id64,
       p.system,
       p.sector,
       r.region,
       p.mass_code,
       TRUE AS is_predicted,
       p.x, p.y, p.z
FROM system_predicted p
-- Region has to come the long way round, through the sector NAME: system_predicted
-- carries no region_id and no sector_id, only the parsed sector string. All 2,269,024
-- rows resolve, so JOIN rather than LEFT JOIN would be safe -- LEFT anyway, for the
-- same reason as above.
LEFT JOIN sector sc ON sc.sector    = p.sector
LEFT JOIN region r  ON r.region_id  = sc.region_id
WHERE NOT p.is_catalog;

-- --------------------------------------------------------------------------
-- COMMENTS. Kept in this file, beside the DDL they describe, so a schema change
-- and its documentation cannot drift apart. Re-applied by etl/build_system_all.py on
-- every run, because CREATE OR REPLACE VIEW drops all of them.
-- --------------------------------------------------------------------------

COMMENT ON VIEW system_all IS
'Every system we can name, observed and inferred, with its human-readable system, sector and region names and its mass code. 197,826,126 rows: 197,764,363 observed (is_predicted FALSE) plus 61,763 boxel-predicted (TRUE). A VIEW over system_known, system_predicted, sector and region -- nothing is stored, and it costs whatever the query over it costs.

*** ONE ROW PER SYSTEM. The catalogued half of system_predicted is EXCLUDED on purpose. *** system_predicted holds two populations and only one of them is a system we inferred: all 2,207,261 is_catalog rows resolve to a system_known row by id64 (measured, 100%), while all 61,763 boxel rows resolve to none. Including both halves would list 2.2M systems twice -- once observed, once predicted -- and silently inflate every count taken over this view. Those systems are still here, in the observed half, which is what they are.

*** is_predicted MEANS "WE INFERRED THIS SYSTEM EXISTS", NOT "WE HAVE ODDS FOR IT". *** A TRUE row is a Stellar-Forge-implied system in no dump anywhere, so it has BOXEL-CENTROID coordinates only -- x/y/z are good to about +/-640 ly at mass code h, and you can arrive and find nothing at the exact spot. A FALSE row has exact coordinates. Never compare the two on distance without saying which is which. For the per-target probabilities, join system_predicted directly; they are deliberately not here, because this view answers "what systems are there and what are they called".

Joining back: id64 is the game''s own key and is present on both halves EXCEPT the boxel rows, where it is NULL for all 61,763 -- a system nobody has reported has no id64 to know. system_id is NULL on every predicted row by construction. Use system when you need a key that spans both.

DERIVED view: schema/system_all.sql, applied by etl/build_system_all.py.';

COMMENT ON COLUMN system_all.system_id IS
'The model''s own surrogate key from system_known, NOT the game''s id64 and not derived from anything. NULL on every predicted row -- a boxel prediction has no system_known parent to take one from, which is the whole reason system_predicted declares no foreign key. Use it to join back to system_known, system_body or poi; use system when the join has to cover both halves.';

COMMENT ON COLUMN system_all.id64 IS
'The game''s own 64-bit system address. Present on the observed half, and NULL on ALL 61,763 predicted rows -- a system nobody has reported has never been assigned one we could read. Do not use it as the join key for this view for that reason.';

COMMENT ON COLUMN system_all.system IS
'The full name the game uses, composed for the observed half as sector || '' '' || "system" and taken verbatim from system_predicted for the inferred half. THE ONLY KEY THAT SPANS BOTH HALVES. Hand-named systems (Sol, Colonia, 61 Ursae Majoris) stand alone: sector_id = 0 is the ''crafted'' SENTINEL and its name is not prefixed. Test that by sector_id and never by sector.is_crafted, which is TRUE for 424 real named sectors as well.';

COMMENT ON COLUMN system_all.sector IS
'Human-readable sector name (''Blaa Hypai''). NULL for the 149,749 hand-named systems, which carry no sector in their name -- that is a real absence and not a gap to fill. Every one of the 2,269,024 system_predicted rows resolves to a sector row, so this is never NULL on the inferred half.';

COMMENT ON COLUMN system_all.region IS
'Human-readable name of the galactic region, one of the game''s 42 hand-drawn regions (''Inner Orion Spur''). Reached two different ways by the two halves: directly from system_known.region_id, which is populated in all 197,764,363 rows, and for predicted systems the long way through the sector name to sector.region_id. Nullable by declaration on both sides rather than by observation -- the joins are LEFT so a lapsed assumption shows up as a NULL region instead of a silently shorter view.';

COMMENT ON COLUMN system_all.mass_code IS
'The size class of the generator cube the system sits in, ''a'' (smallest) to ''h'' (largest), read straight off the name. THE STRONGEST SINGLE PREDICTOR IN THE PROJECT: Wolf-Rayets are effectively absent outside h, and p_bh runs about 0.46 at h against 0.04 at e. NULL for the 149,724 hand-named systems, which have no procedural name to read it from.';

COMMENT ON COLUMN system_all.is_predicted IS
'FALSE if somebody has actually reported this system (it came from system_known), TRUE if we merely inferred that it exists from a gap in the Stellar Forge boxel index. *** THE TWO ARE NOT INTERCHANGEABLE AND THIS COLUMN IS THE ONLY THING THAT SAYS SO. *** A TRUE row is a place worth flying to and never evidence anything is there; its coordinates are a boxel centroid, up to 1280 ly across. It also means nobody has been there, which for an explorer is the point. Only 61,763 rows are TRUE, and RECOMMENDATIONS.md R2/R3 warn that this layer is thin and heavily CORE-BIASED -- a lower bound, and not a usable basis for fringe estimates.';

COMMENT ON COLUMN system_all.x IS
'Galactic x in light-years. EXACT on the observed half; a BOXEL CENTROID where is_predicted, good to roughly +/-640 ly at mass code h. Filter on is_predicted before measuring any distance you intend to trust.';

COMMENT ON COLUMN system_all.y IS
'Galactic y in light-years. EXACT on the observed half; a BOXEL CENTROID where is_predicted -- see system_all.x.';

COMMENT ON COLUMN system_all.z IS
'Galactic z in light-years. EXACT on the observed half; a BOXEL CENTROID where is_predicted -- see system_all.x.';

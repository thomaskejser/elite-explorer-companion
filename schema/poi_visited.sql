-- poi_visited: POI systems the commander has actually arrived in.
-- Database: elite_mapping_v2_current.duckdb (app state).
-- Lives in schema/ with the model tables: one directory, one file per table.
-- Load order tier 1.
CREATE TABLE IF NOT EXISTS poi_visited (
    system VARCHAR NOT NULL PRIMARY KEY,
    id64        BIGINT,
    sector      VARCHAR,
    poi_id      INTEGER,
    poi         VARCHAR,
    poi_class   VARCHAR,
    visited_utc TIMESTAMP
);

-- --------------------------------------------------------------------------
-- COMMENTS.
-- --------------------------------------------------------------------------

COMMENT ON TABLE poi_visited IS
'APP STATE: one row per point-of-interest system the commander has ARRIVED IN. Written by the overlay the moment the journal shows a jump into a system carrying a POI -- ARRIVING is the criterion, not scanning, because a phenomenon is in the nav panel from the moment you drop in. Its job is RETIREMENT: once you have been there the system has nothing left to offer and must stop competing for a waypoint slot. Contrast the two verbs this database uses, which are NOT interchangeable: SEEN means the galaxy map revealed it (system_seen), VISITED means the commander actually went there. This table is a visited table. *** A POI is not a claim, and this must NEVER be read as "already taken". *** The game credits a Lagrange cloud or a green giant to YOU however many commanders logged it first -- exactly what separates POIs from rare-star prediction, where a black hole somebody already scanned is worth nothing. This table means "I have been there", not "it is used up". Migrated from input/unmigrated/poi_seen.json; its pre-GGG name input/unmigrated/nsp_seen.json is fully subsumed, the union being the same 704 systems. *** WRITE BOUNDARY: elite_mapping_v2_current.duckdb is the ONLY database the app may write to. *** The model database is background information the app READS -- fully rebuilt by etl/, so anything written there would be silently erased. attach_model() enforces this by attaching the model READ_ONLY.';

COMMENT ON COLUMN poi_visited.system IS
'The game''s full system name and the NATURAL KEY, from the journal. SYSTEM-grained, not body-grained: the store this replaces recorded arrival only, and arrival is the criterion. A system holding several POIs is still one row.';

COMMENT ON COLUMN poi_visited.id64 IS
'The game''s 64-bit system id, resolved by common.current.resolve_id64() against the model''s system_known, by name. A name that belongs to MORE THAN ONE system is left NULL rather than resolved to whichever star sorted first -- 1,477 composed names are held by 2 or more systems, nearly all catalogue designations like ''2MASS J03285461+3116512'', and none has yet reached this database. NOT a foreign key (cross-database). Only 382 of the 704 migrated systems are in system_known at all, so NULL is the majority case here and not an anomaly.';

COMMENT ON COLUMN poi_visited.poi_id IS
'Which KIND of POI, pointing at poi.poi_id in the MODEL database. *** NULL for the overwhelming majority of migrated rows -- 16 of 704 resolve *** -- which is a property of the source and not a defect here: input/unmigrated/poi_seen.json recorded only that you had been to a system, never what was in it, so the kind can be recovered only by asking the model, and the model has no id_poi for a system it has never heard of. Rows the overlay writes from now on carry it, because the overlay knows which POI it routed you to. NOT a foreign key: the target is in another database.';

COMMENT ON COLUMN poi_visited.poi IS
'The POI''s human label, denormalised from the model''s poi dimension so the row keeps its meaning standalone -- the same reasoning that makes system_confirmed carry coordinates instead of a reference. NULL wherever poi_id is NULL.';

COMMENT ON COLUMN poi_visited.poi_class IS
'Coarse grouping copied from poi.poi_class: nsp, anomaly, ggg, guardian, thargoid, gec. This is the granularity at which a single value is nearly lossless -- only 8 systems in the whole galaxy hold more than one CLASS -- which is what makes one row per system defensible.';

COMMENT ON COLUMN poi_visited.visited_utc IS
'When the arrival was recorded. NULL for every MIGRATED row -- the JSON store was a bare list of names -- so NULL means "before the migration", not "unknown recently". Populated going forward from the journal event timestamp.';

COMMENT ON COLUMN poi_visited.sector IS
'Procedural sector name, DERIVED from system at write time. NULL for hand-named systems. See system_seen.sector.';

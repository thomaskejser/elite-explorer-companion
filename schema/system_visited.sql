-- system_visited: systems this commander has actually been to.
-- Database: elite_mapping_v2_current.duckdb (app state).
-- Load order tier 1. Deliberately NOT a child of system_seen -- see the table comment.
CREATE TABLE IF NOT EXISTS system_visited (
    system       VARCHAR NOT NULL PRIMARY KEY,
    id64              BIGINT,
    sector            VARCHAR,
    first_visited_utc TIMESTAMP,
    last_visited_utc  TIMESTAMP
);

-- --------------------------------------------------------------------------
-- COMMENTS.
-- --------------------------------------------------------------------------

COMMENT ON TABLE system_visited IS
'APP STATE: one row per system the commander has actually ARRIVED IN, harvested from every journal event that carries a StarPos. Its job is DURABILITY, not analysis -- Elite deletes old journals, so a target retired by visiting it would come back as a suggestion the moment its journal aged out. The store is the only thing that makes "been there" permanent. *** NOT a subset of system_seen, and there is no foreign key between them: 7 of the 3,099 rows here were never seen first. *** You can arrive somewhere you never plotted to -- an in-system honk after a random jump, or a visit predating the starclass harvest -- so treating visited as "seen and then flown to" would silently drop those. Migrated from input/unmigrated/visited.json. Visiting a system says nothing about whether it was WORTH visiting: system_outcome (if adopted) carries the verdict. *** WRITE BOUNDARY: elite_mapping_v2_current.duckdb is the ONLY database the app may write to. *** The model database (elite_mapping_v2.duckdb) is background information the app READS -- it is derived from input/ and raw/ and fully rebuilt by etl/, so anything the app wrote there would be silently erased by the next merge. attach_model() enforces this by attaching the model READ_ONLY.';

COMMENT ON COLUMN system_visited.system IS
'The game''s full system name and the NATURAL KEY, verbatim from the journal''s StarSystem field. Matches system_seen.system where both exist.';

COMMENT ON COLUMN system_visited.id64 IS
'The game''s 64-bit system id, resolved against elite_mapping_v2.duckdb''s staging.sys_bridge. NOT a foreign key -- cross-database FKs are not enforceable in DuckDB. Expected to be non-NULL far more often than on system_seen: you can only fly to a system that exists, whereas a seen system may be a prediction nobody has ever reported.';

COMMENT ON COLUMN system_visited.first_visited_utc IS
'Timestamp of the earliest arrival on record. NULL for every MIGRATED row -- input/unmigrated/visited.json stored a bare list of names and threw the times away. Populated going forward.';

COMMENT ON COLUMN system_visited.last_visited_utc IS
'Timestamp of the most recent arrival. NULL for migrated rows. Distinct from first_visited_utc because revisits are common and normal -- a carrier system or a route staging point gets passed through repeatedly -- so neither one alone tells you whether a visit is fresh.';

COMMENT ON COLUMN system_visited.sector IS
'Procedural sector name, DERIVED from system at write time. NULL for hand-named systems -- 630 of 3,108 rows here, because named space IS the inhabited bubble and that is where a commander spends time before heading out. See system_seen.sector for the derivation and why it is stored.';

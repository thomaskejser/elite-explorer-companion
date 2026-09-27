-- system_seen: what Elite has REVEALED to us, without our having gone there.
-- Database: elite_mapping_v2_current.duckdb (app state), NOT elite_mapping_v2.duckdb.
-- Lives in schema/ with the model tables: one directory, one file per table, no exceptions.
-- Load order tier 1. Nothing references it; it references nothing.
CREATE TABLE IF NOT EXISTS system_seen (
    system    VARCHAR NOT NULL PRIMARY KEY,
    star_class     VARCHAR,
    x              DOUBLE,
    y              DOUBLE,
    z              DOUBLE,
    id64           BIGINT,
    sector         VARCHAR,
    first_seen_utc TIMESTAMP,
    is_known       BOOLEAN
);

-- --------------------------------------------------------------------------
-- COMMENTS. Kept in this file, beside the DDL they describe, so a schema change
-- and its documentation cannot drift apart.
-- --------------------------------------------------------------------------

COMMENT ON TABLE system_seen IS
'APP STATE: one row per system Elite has REVEALED to this commander without a visit -- the arrival star class and, where known, the exact coordinates. Two journal facts feed it and they are NOT the same event: plotting a route rewrites NavRoute.json with a StarClass AND a StarPos for every hop, whereas FSDTarget/StartJump name a class only. That is why star_class is populated for every row today (12,243) and x/y/z for barely half (6,757) -- position is the scarcer fact, not the commoner one. *** This is knowledge, not travel: seeing a system here means the galaxy map told us what its primary star is, which for an uncatalogued H or W* is a CONFIRMED FIND the moment it appears, thousands of ly before anyone flies there. *** Migrated from input/unmigrated/starclass.json + input/unmigrated/starpos.json, which are one grain split across two files. Do NOT treat absence from this table as "unknown to us": system_visited holds 7 systems that were never seen first. *** WRITE BOUNDARY: elite_mapping_v2_current.duckdb is the ONLY database the app may write to. *** The model database (elite_mapping_v2.duckdb) is background information the app READS -- it is derived from input/ and raw/ and fully rebuilt by etl/, so anything the app wrote there would be silently erased by the next merge. attach_model() enforces this by attaching the model READ_ONLY.';

COMMENT ON COLUMN system_seen.system IS
'The game''s full system name and the NATURAL KEY, exactly as the journal spells it ("Blaa Hypai BA-A g5"). Name and not id64 because that is all the journal gives at reveal time -- a plotted hop carries StarClass and StarPos but no id64 -- so a name-keyed row can be written the instant the fact arrives, and id64 resolved later or never.';

COMMENT ON COLUMN system_seen.star_class IS
'Arrival (primary) star class verbatim from the journal: the 28 distinct values include H, N, W/WN/WC/WO, AeBe, TTS and the ordinary OBAFGKM. *** The single most valuable column in this database ***: H or W* on a system that no catalogue lists is a black hole or Wolf-Rayet found by us. NULL is permitted because a galaxy-map position can be learned without a class, though no such row exists yet.';

COMMENT ON COLUMN system_seen.x IS
'Exact galactic X from the journal''s StarPos. NULL when only the class was revealed. EXACTNESS IS THE POINT: a predicted system carries its BOXEL CENTROID until something reveals the truth, and for mass code h the centroid is up to +/-640 ly out -- five candidates all reading the same distance is the visible symptom. One plotted route replaces the centroid with this.';

COMMENT ON COLUMN system_seen.y IS
'Exact galactic Y from the journal''s StarPos. NULL when only the class was revealed. See system_seen.x.';

COMMENT ON COLUMN system_seen.z IS
'Exact galactic Z from the journal''s StarPos. NULL when only the class was revealed. See system_seen.x.';

COMMENT ON COLUMN system_seen.id64 IS
'The game''s 64-bit system id, resolved by common.current.resolve_id64() -- it matches this row''s name against the model''s system_known composed through full_name_sql(). A name that belongs to MORE THAN ONE system is left NULL rather than resolved to whichever star sorted first -- 1,477 composed names are held by 2 or more systems, nearly all catalogue designations like ''2MASS J03285461+3116512'', and none has yet reached this database. NULLABLE AND EXPECTED TO BE NULL for a good fraction of rows: a system we reached by prediction is one nobody has reported, so it is frequently absent from system_known altogether -- which is precisely why it was worth flying to. NOT a foreign key: the referenced table is in a DIFFERENT DATABASE and DuckDB cannot enforce a cross-database FK. Join on it, never rely on it.';

COMMENT ON COLUMN system_seen.first_seen_utc IS
'When the reveal was first recorded. NULL for every row MIGRATED from the JSON stores, which kept no timestamp -- absence means "before the migration", not "unknown recently". Populated going forward.';

COMMENT ON COLUMN system_seen.sector IS
'Procedural sector name, DERIVED from system AT WRITE TIME and stored rather than re-parsed on every read. Everything the overlay asks is scoped to the sector the commander is currently in, and a stored column turns that into an equality test. The alternative was matching a name PREFIX, which is slower and wrong at the edges -- a LIKE ''Prua Ploe%'' quietly also matches ''Prua Ploes''. Derived by common.current.SECTOR_SQL, which is the ONE definition; it was validated to agree exactly with the model''s own system_predicted.sector over 50,000 rows and with app.names.sector_of over every app-state name. NULL for hand-named systems (Sol, Achenar, 61 Ursae Majoris): those have no procedural sector, which is not a parse failure but the inhabited bubble -- and the bubble is fully explored, so it holds no predictions anyway.';

COMMENT ON COLUMN system_seen.is_known IS
'TRUE if this system is ALREADY IN THE DUMPS -- present in the model''s system_known, whose own comment reads "observed, NOT predicted -- every row is a system somebody has actually reported". Reporting a system means honking it, and honking DISCOVERS the arrival star, so a TRUE here means the rare object we spotted already has somebody else''s name on it. *** THIS IS WHAT SEPARATES A FIND FROM A SIGHTING, and the overlay''s Confirmed table shows only the FALSE rows. Roughly two in five sightings are already reported, and the proportion is far higher for the most-hunted classes: essentially every confirmed black hole and Wolf-Rayet sits beside a route somebody else has already plotted. An empty BH column in that table is therefore a true statement about the galaxy, not a broken query. *** NULL MEANS NOT YET CHECKED, NOT "unknown to the dumps". *** Unlike id64 it is resolved WITHOUT opening the model: common.current.resolve_known() reads the mirror in this very database -- model.system_predicted for the rows it can settle exactly, then model.system_known_probe for the rest -- so the overlay can answer it while a merge is halfway through rewriting the 60 GiB file. Every loader calls it via finish(); the overlay resolves it too, but only after a route plot writes new rows, because the probe is a 6.9M-row scan. Treat NULL as "show it" -- the alternative hides a genuine find until a loader has run. A FALSE can become TRUE later when somebody else reports the system, which is why resolve_known re-checks every row that is not already TRUE; TRUE never reverts.';

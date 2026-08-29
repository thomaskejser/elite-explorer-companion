-- system_confirmed: rare finds this commander has personally confirmed.
-- Database: elite_mapping_v2_current.duckdb (app state).
-- Lives in schema/ with the model tables: one directory, one file per table.
-- Load order tier 1. Deliberately standalone -- see the table comment.
CREATE TABLE IF NOT EXISTS system_confirmed (
    system   VARCHAR NOT NULL PRIMARY KEY,
    kind          VARCHAR NOT NULL,
    star_class    VARCHAR,
    mass_code     VARCHAR,
    x             DOUBLE,
    y             DOUBLE,
    z             DOUBLE,
    id64          BIGINT,
    sector        VARCHAR,
    was_exact     BOOLEAN,
    was_predicted BOOLEAN,
    visited       BOOLEAN NOT NULL,
    found_date    DATE,
    is_known      BOOLEAN
);

-- --------------------------------------------------------------------------
-- COMMENTS. Kept in this file, beside the DDL they describe, so a schema change
-- and its documentation cannot drift apart.
-- --------------------------------------------------------------------------

COMMENT ON TABLE system_confirmed IS
'APP STATE: the log of what this tool has actually TURNED UP -- one row per system whose arrival class Elite revealed to be a black hole or Wolf-Rayet that no catalogue lists. A certain find and not a candidate: the class came from the game, so there is nothing left to verify. *** THIS IS THE LEAST REPRODUCIBLE TABLE IN THE PROJECT. *** Everything else can be rebuilt from a download; these rows are the output of actual flying. It is deliberately STANDALONE -- carrying name, class, mass code AND coordinates rather than referencing a candidate row -- because the prediction tables get rebuilt, and when a rebuild drops a name (EDAstro catalogued it, the boxel enumeration changed) the knowledge that YOU found it there would vanish with the reference. Rows are NEVER deleted, only marked visited. *** WRITE BOUNDARY: elite_mapping_v2_current.duckdb is the ONLY database the app may write to. *** The model database is background information the app READS -- derived from input/ and raw/ and fully rebuilt by etl/, so anything the app wrote there would be silently erased by the next merge. attach_model() enforces this by attaching the model READ_ONLY. Migrated from app/confirmed.json.';

COMMENT ON COLUMN system_confirmed.system IS
'The game''s full system name and the NATURAL KEY, as the journal spells it. The only identifier guaranteed to be present: a system nobody has reported has no id64 to look up, and being unreported is the normal case for a find.';

COMMENT ON COLUMN system_confirmed.kind IS
'''BH'' or ''WR'' -- the classification of star_class, STORED rather than derived so the row keeps its meaning if the classifier changes. NOT NULL: a row that is neither is not a find and does not belong here.';

COMMENT ON COLUMN system_confirmed.star_class IS
'The raw arrival class Elite reported: H or SupermassiveBlackHole for a black hole, W/WN/WC/WO for a Wolf-Rayet. Kept alongside `kind` because the sub-type matters -- WO and WC are far rarer than WN -- and so a future reclassification can re-derive kind from it.';

COMMENT ON COLUMN system_confirmed.mass_code IS
'Procedural mass code a-h, from the system name at the time of the find. Recorded per row rather than re-parsed, so a find can be scored against whatever the model believed for that mass code even after the name parser changes.';

COMMENT ON COLUMN system_confirmed.x IS
'Exact galactic X. Present for every row: a confirmed find always arrived with a NavRoute hop or a jump, both of which carry StarPos. This is what makes the row navigable on its own, with no lookup and no model database.';

COMMENT ON COLUMN system_confirmed.y IS
'Exact galactic Y. See system_confirmed.x.';

COMMENT ON COLUMN system_confirmed.z IS
'Exact galactic Z. See system_confirmed.x.';

COMMENT ON COLUMN system_confirmed.id64 IS
'The game''s 64-bit system id, resolved against the model''s staging.sys_bridge. NOT a foreign key -- cross-database FKs are not enforceable in DuckDB -- and EXPECTED to be NULL often, because an uncatalogued find is precisely a system the catalogues do not have.';

COMMENT ON COLUMN system_confirmed.was_exact IS
'TRUE if the coordinates came from the game (a NavRoute hop), FALSE if a BOXEL CENTROID was standing in. Worth keeping: a centroid is up to +/-640 ly out at mass code h, so a FALSE row is one to re-fix before flying to it.';

COMMENT ON COLUMN system_confirmed.was_predicted IS
'TRUE if the system came from the PREDICTED pool -- a boxel gap the model proposed that nobody had reported -- rather than a known-but-unscanned system. *** This is the column that scores the model. *** A predicted find is evidence the gap enumeration works; an unscanned find is only evidence that scanning pays.';

COMMENT ON COLUMN system_confirmed.visited IS
'TRUE once the commander has actually been there. FALSE is the normal state at discovery: the class is revealed by PLOTTING A ROUTE, which usually happens thousands of ly off the current heading, so a find must survive being out of range for a long time. This is the ONLY field that changes after insert.';

COMMENT ON COLUMN system_confirmed.found_date IS
'Date the find was recorded (UTC). A DATE and not a TIMESTAMP because that is all app/confirmed.json ever kept.';

COMMENT ON COLUMN system_confirmed.sector IS
'Procedural sector name, DERIVED from system at write time. This is what makes "which confirmed finds are waiting in THIS sector" a single equality predicate rather than a scan with a LIKE -- and that question is the whole point of the overlay''s Confirmed table. See system_seen.sector.';

COMMENT ON COLUMN system_confirmed.is_known IS
'TRUE if this system is ALREADY IN THE DUMPS -- present in the model''s system_known, whose own comment reads "observed, NOT predicted -- every row is a system somebody has actually reported". Reporting a system means honking it, and honking DISCOVERS the arrival star, so a TRUE here means the rare object we spotted already has somebody else''s name on it. *** THIS IS WHAT SEPARATES A FIND FROM A SIGHTING, and the overlay''s Confirmed table shows only the FALSE rows. *** Measured when the column went in: 408 of 1,087 confirmed systems were already reported -- including ALL 11 black holes and ALL 9 Wolf-Rayets, because black holes are the most-hunted objects in the game and these sat beside plotted routes. An empty BH column in that table is therefore a true statement about the galaxy, not a broken query. *** NULL MEANS NOT YET CHECKED, NOT "unknown to the dumps". *** Like id64 it is resolved against staging.sys_bridge by common.current.resolve_known(), which every loader calls via finish(); the overlay resolves it too, but only after a route plot writes new rows, because the probe is a scan of a 197M-row table and costs about 700 ms. Treat NULL as "show it" -- the alternative hides a genuine find until a loader has run. A FALSE can become TRUE later when somebody else reports the system, which is why resolve_known re-checks every row that is not already TRUE; TRUE never reverts.';

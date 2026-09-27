-- system_confirmed: rare finds this commander has personally confirmed.
-- EVERY kind this project predicts, not just BH/WR -- see the `kind` comment.
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
'APP STATE: the log of what this tool has actually TURNED UP -- one row per system whose arrival class Elite revealed to be one of the rare objects this project predicts: black hole, Wolf-Rayet, Herbig Ae/Be, supergiant, O-type, neutron star or white dwarf. *** EVERY PREDICTED KIND BELONGS HERE, NOT JUST BH AND WR. *** Database.promote_confirmed() copies rare sightings across from system_seen on every start and on every reveal, so a kind missing from this table means the promotion is not running, not that the galaxy is empty of it. A certain find and not a candidate: the class came from the game, so there is nothing left to verify. *** THIS IS THE LEAST REPRODUCIBLE TABLE IN THE PROJECT. *** Everything else can be rebuilt from a download; these rows are the output of actual flying. It is deliberately STANDALONE -- carrying name, class, mass code AND coordinates rather than referencing a candidate row -- because the prediction tables get rebuilt, and when a rebuild drops a name (EDAstro catalogued it, the boxel enumeration changed) the knowledge that YOU found it there would vanish with the reference. Rows are NEVER deleted, only marked visited. *** WRITE BOUNDARY: elite_mapping_v2_current.duckdb is the ONLY database the app may write to. *** The model database is background information the app READS -- derived from input/ and raw/ and fully rebuilt by etl/, so anything the app wrote there would be silently erased by the next merge. attach_model() enforces this by attaching the model READ_ONLY. Migrated from input/unmigrated/confirmed.json.';

COMMENT ON COLUMN system_confirmed.system IS
'The game''s full system name and the NATURAL KEY, as the journal spells it. The only identifier guaranteed to be present: a system nobody has reported has no id64 to look up, and being unreported is the normal case for a find.';

COMMENT ON COLUMN system_confirmed.kind IS
'One of ''BH'', ''WR'', ''SUPERGNT'', ''HERBIG'', ''O-TYPE'', ''NEUTRON'', ''WHT DWRF'' -- the classification of star_class, STORED rather than derived so the row keeps its meaning if the classifier changes. The one definition of the mapping is app/kinds.py:KINDS -- the `key` field, which the promotion SQL is generated from, so this list cannot drift from what the app writes. *** THESE STRINGS ARE FROZEN. *** They are the `key` and never the `abbr`: this database is the one in the project that cannot be rebuilt, so renaming a kind would leave old rows under the old spelling and new rows under the new one, and every count of that kind would be wrong from then on. The overlay shows `abbr` instead (BH displays as ''BLK HOLE''), which is what to change when a label should read differently. NOT NULL: a row that classifies as nothing is not a find and does not belong here.';

COMMENT ON COLUMN system_confirmed.star_class IS
'The raw arrival class Elite reported: H or SupermassiveBlackHole for a black hole, W/WN/WC/WO for a Wolf-Rayet, O, AeBe, N, the five *_SuperGiant spellings, or any of the fifteen D* white-dwarf variants. Kept alongside `kind` because the sub-type matters -- WO and WC are far rarer than WN -- and so a future reclassification can re-derive kind from it.';

COMMENT ON COLUMN system_confirmed.mass_code IS
'Procedural mass code a-h, from the system name at the time of the find. Recorded per row rather than re-parsed, so a find can be scored against whatever the model believed for that mass code even after the name parser changes.';

COMMENT ON COLUMN system_confirmed.x IS
'Exact galactic X. NULL for 413 of the promoted rows and NOT for every row, which the previous wording claimed: that held while only BH/WR migrated from confirmed.json were here, all of which came from a NavRoute hop. A bare FSDTarget carries StarClass WITHOUT StarPos, so a class can be known with no position at all -- see was_exact. Where it IS present it is what makes the row navigable on its own, with no lookup and no model database.';

COMMENT ON COLUMN system_confirmed.y IS
'Exact galactic Y. See system_confirmed.x.';

COMMENT ON COLUMN system_confirmed.z IS
'Exact galactic Z. See system_confirmed.x.';

COMMENT ON COLUMN system_confirmed.id64 IS
'The game''s 64-bit system id, resolved by common.current.resolve_id64() against the model''s system_known, by name. A name that belongs to MORE THAN ONE system is left NULL rather than resolved to whichever star sorted first -- 1,477 composed names are held by 2 or more systems, nearly all catalogue designations like ''2MASS J03285461+3116512'', and none has yet reached this database. NOT a foreign key -- cross-database FKs are not enforceable in DuckDB -- and EXPECTED to be NULL often, because an uncatalogued find is precisely a system the catalogues do not have.';

COMMENT ON COLUMN system_confirmed.was_exact IS
'TRUE if the coordinates came from the game (a NavRoute hop), FALSE otherwise. Worth keeping either way, because a FALSE row is one to re-fix before flying to it -- but FALSE means two different things by origin. On a row migrated from confirmed.json it means a BOXEL CENTROID was standing in, up to +/-640 ly out at mass code h. On a row written by Database.promote_confirmed() it means NO COORDINATES AT ALL: the class arrived on a bare FSDTarget, which carries StarClass without StarPos, so x/y/z are NULL rather than approximate. That is the stronger reason to re-fix, not the weaker one.';

COMMENT ON COLUMN system_confirmed.was_predicted IS
'TRUE if the system came from the PREDICTED pool -- a boxel gap the model proposed that nobody had reported -- rather than a known-but-unscanned system. Written as system_predicted.is_catalog = FALSE, which the schema defines as in NO dump, so it is exactly ''we called this one''. *** This is the column that scores the model. *** A predicted find is evidence the gap enumeration works; an unscanned find is only evidence that scanning pays. *** IT IS ZERO FOR EVERY NEUTRON AND EVERY WHITE DWARF, and that is a true statement rather than a broken join. *** The boxel-predicted half carries mass codes e/f/g/h ONLY, while 1,099 of 1,234 confirmed neutrons are mass code d -- the pool is built for BH/WR/Herbig/supergiant/O-type, and neutrons and white dwarfs are byproducts of flying it, not things it proposes. Scoring: O-TYPE 92 of 321, WR 18 of 32, HERBIG 14 of 130, BH 2 of 70.';

COMMENT ON COLUMN system_confirmed.visited IS
'TRUE once the commander has actually been there. FALSE is the normal state at discovery: the class is revealed by PLOTTING A ROUTE, which usually happens thousands of ly off the current heading, so a find must survive being out of range for a long time. This is the ONLY field that changes after insert.';

COMMENT ON COLUMN system_confirmed.found_date IS
'Date the find was recorded (UTC). A DATE and not a TIMESTAMP because that is all input/unmigrated/confirmed.json ever kept. Promoted rows take it from system_seen.first_seen_utc and NEVER from the day the promotion ran -- stamping historic finds with one date would destroy the only thing this column is for. NULL where the sighting predates that column.';

COMMENT ON COLUMN system_confirmed.sector IS
'Procedural sector name, DERIVED from system at write time. This is what makes "which confirmed finds are waiting in THIS sector" a single equality predicate rather than a scan with a LIKE -- and that question is the whole point of the overlay''s Confirmed table. See system_seen.sector.';

COMMENT ON COLUMN system_confirmed.is_known IS
'TRUE if this system is ALREADY IN THE DUMPS -- present in the model''s system_known, whose own comment reads "observed, NOT predicted -- every row is a system somebody has actually reported". Reporting a system means honking it, and honking DISCOVERS the arrival star, so a TRUE here means the rare object we spotted already has somebody else''s name on it. *** THIS IS WHAT SEPARATES A FIND FROM A SIGHTING, and the overlay''s Confirmed table shows only the FALSE rows. Roughly two in five sightings are already reported, and the proportion is far higher for the most-hunted classes: essentially every confirmed black hole and Wolf-Rayet sits beside a route somebody else has already plotted. An empty BH column in that table is therefore a true statement about the galaxy, not a broken query. *** NULL MEANS NOT YET CHECKED, NOT "unknown to the dumps". *** Unlike id64 it is resolved WITHOUT opening the model: common.current.resolve_known() reads the mirror in this very database -- model.system_predicted for the rows it can settle exactly, then model.system_known_probe for the rest -- so the overlay can answer it while a merge is halfway through rewriting the 60 GiB file. Every loader calls it via finish(); the overlay resolves it too, but only after a route plot writes new rows, because the probe is a 6.9M-row scan. Treat NULL as "show it" -- the alternative hides a genuine find until a loader has run. A FALSE can become TRUE later when somebody else reports the system, which is why resolve_known re-checks every row that is not already TRUE; TRUE never reverts.';

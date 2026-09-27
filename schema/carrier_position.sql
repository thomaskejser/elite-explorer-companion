-- carrier_position: where each fleet carrier is, as coordinates and a pasteable name.
-- Database: elite_mapping_v2.duckdb (the model).
-- Load order tier 3 -- derived from carrier and system_known, so both must exist first.
CREATE TABLE IF NOT EXISTS carrier_position (
    callsign VARCHAR NOT NULL PRIMARY KEY,
    system   VARCHAR,
    x        DOUBLE,
    y        DOUBLE,
    z        DOUBLE
);

-- --------------------------------------------------------------------------
-- COMMENTS. Kept in this file, beside the DDL they describe, so a schema change
-- and its documentation cannot drift apart.
-- --------------------------------------------------------------------------

COMMENT ON TABLE carrier_position IS
'Where each fleet carrier is, resolved once: 88,175 rows, one per carrier that has a position, of the 88,495 in carrier. *** THIS TABLE EXISTS FOR LATENCY. *** "Which reliable carriers are nearest" is asked on every jump, and answering it from carrier alone resolves 2,524 carriers through system_known (200,676,922 rows) with nothing to probe on, so DuckDB scans the lot: 1,440 ms warm, 5,224 ms cold, on a single-threaded event loop where that is the HUD frozen. Here it is 1.8 ms. Same precedent as system_neutron. *** IT ADDS NO FACTS *** -- every value is copied from system_known, so read carrier''s own comment for the trap that matters: a carrier can jump at any moment and neither table would know. REBUILD WHENEVER carrier IS RELOADED; a carrier that moved keeps its stale position here until you do. DERIVED table: etl/carrier_position/refresh.py.';

COMMENT ON COLUMN carrier_position.callsign IS
'The game''s own carrier identifier ("X9K-T7Q"), the natural key, REFERENCING carrier.callsign -- checked by common.db.check_references, not by a constraint. Keyed on the callsign because that is what carrier is keyed on and what the overlay joins back to for the name and the is_reliable flag: this table answers "where", carrier answers "what".';

COMMENT ON COLUMN carrier_position.system IS
'The FULL, PASTEABLE system name ("Colonia", "Blau Eaec RY-S e3-2"), composed once here. *** THE sector_id = 0 SENTINEL IS ALREADY HANDLED *** -- a hand-named system composes as "crafted Colonia" if you concatenate blindly, which the galaxy map rejects. That was a live bug in three queries and this was the worst hit: 2,044 of the 2,524 reliable carriers are in hand-named systems, so most nearest-carrier names were uncopyable.';

COMMENT ON COLUMN carrier_position.x IS
'Light years, galactic coordinates, copied from system_known. Nullable by declaration, populated on all 88,175 rows. *** THE MISSING CARRIERS ARE MISSING, NOT NULL: *** 320 of the 88,495 in carrier have no system_id to resolve (34 carry no SystemAddress, 288 sit in systems system_known has never heard of), so they have no row here at all. Exactly ONE is reliable, and it can never appear in a "nearest" list -- we do not know where it is.';

COMMENT ON COLUMN carrier_position.y IS
'Light years, galactic coordinates, copied from system_known. See carrier_position.x.';

COMMENT ON COLUMN carrier_position.z IS
'Light years, galactic coordinates, copied from system_known. See carrier_position.x.';

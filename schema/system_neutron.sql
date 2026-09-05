-- system_neutron: the systems whose PRIMARY (= arrival) star is a neutron star.
-- Database: elite_mapping_v2.duckdb (the model).
-- Load order tier 2 (needs sector, region, body, poi) -- SAME LAYOUT AS system_known,
-- column for column, key for key, foreign key for foreign key. It is a subset of that
-- table and nothing more, so anything that reads system_known reads this unchanged.
CREATE TABLE IF NOT EXISTS system_neutron (
    system_id   BIGINT  NOT NULL PRIMARY KEY,
    sector_id   BIGINT  NOT NULL,
    system_in_sector VARCHAR NOT NULL,
    cube_id     VARCHAR,
    mass_code   VARCHAR,
    sub_cube_id INTEGER,
    boxel_index INTEGER,
    region_id   BIGINT,
    primary_star_body_id INTEGER,
    body_count  INTEGER,
    x           DOUBLE,
    y           DOUBLE,
    z           DOUBLE,
    id_poi      INTEGER,
    -- NO UNIQUE constraint, for the same reason system_known has none: 96 id64 values
    -- map to two rows each there, and this inherits both.
    id64        BIGINT,
    UNIQUE (sector_id, system_in_sector),
    FOREIGN KEY (sector_id) REFERENCES sector (sector_id),
    FOREIGN KEY (region_id) REFERENCES region (region_id),
    FOREIGN KEY (primary_star_body_id) REFERENCES body (body_id),
    FOREIGN KEY (id_poi) REFERENCES poi (poi_id)
);

-- --------------------------------------------------------------------------
-- COMMENTS. Kept in this file, beside the DDL they describe, so a schema change
-- and its documentation cannot drift apart. Re-applied by the builder after every
-- merge via common.db.apply_comment_file(), because a migration is the one thing
-- that silently drops a comment.
-- --------------------------------------------------------------------------

COMMENT ON TABLE system_neutron IS
'The 3,427,655 systems whose PRIMARY STAR is a neutron star. SAME LAYOUT AS system_known -- every column, the surrogate key, the natural key and all four foreign keys -- because it IS a subset of system_known and nothing else. Anything written against system_known reads this without modification, and system_id means the same thing in both.

*** BUILT FROM system_known ALONE. *** The membership test is primary_star_body_id = the body row for ''Neutron Star'', which system_known already carries; no other source is consulted and the builder touches no staging table. That matters twice over: the app is not permitted to read staging, and a materialised copy means the overlay''s "three nearest" question is a scan of 3.4M rows instead of 197.6M.

*** PRIMARY STAR IS THE ARRIVAL STAR. *** That is why one column answers the question: you drop out of witchspace at the primary, so a system listed here is a JET CONE BOOST you take without moving -- a 300% FSD supercharge, no supercruise, no detour.

*** EDAstro''s neutron catalogue was considered as the source and REJECTED, and the reason is worth keeping. *** staging.edastro_neutron_star carries an is_arrival_star flag which looks authoritative and is not: it is exactly the test body_name = system_name, all 4,143,570 rows, with no exceptions in either direction. An unnamed primary takes the system''s own name and passes; a primary designated ''A'' -- "Blielee WI-K d8-2 A" -- fails, though it is the same star in the same place. Trusting it would have dropped 1,727,383 perfectly good systems. Where the two sources both have an opinion they agree on all but 2 rows of 1,698,816, so this is a coverage failure in the flag and not a conflict about the galaxy.

*** THESE ARE OTHER PEOPLE''S DISCOVERIES AND THAT IS FINE. *** Every row is a system somebody has already scanned, so there is no first-discovery credit here and none is implied. Unlike the Confirmed table this is deliberately NOT filtered against system_visited: a jet cone works exactly as well the second time you use it. This table is about GETTING somewhere, not about finding something.

COVERAGE IS A FLOOR, NOT A CENSUS. system_known.primary_star_body_id is populated on only 74,274,140 of 197,764,363 rows (37.6%), so a system missing from here may simply be one whose primary nobody has recorded. Never read absence as "no neutron".

DERIVED table: etl/system_neutron/build.py, from system_known.';

COMMENT ON COLUMN system_neutron.system_id IS
'THE SAME SURROGATE KEY AS system_known.system_id, copied and never reallocated -- a row here and the row it came from share an id, so the two tables join directly on it. That is the point of mirroring the layout. Not the game''s id64.';

COMMENT ON COLUMN system_neutron.sector_id IS
'FOREIGN KEY to sector, carried from system_known. Hand-named systems point at the sentinel sector_id = 0 rather than NULL, because a NULL cannot take part in the UNIQUE (sector_id, system_in_sector) key. Compose the full name as sector.sector || '' '' || system_in_sector, except at sector_id = 0 where the name stands alone.';

COMMENT ON COLUMN system_neutron.system_in_sector IS
'The system name WITHOUT its sector prefix ("FC-D d12-1"), exactly as system_known stores it, and half the natural key. The full name -- which is what the galaxy map''s search box wants -- is sector.sector || '' '' || system_in_sector. Named system_in_sector rather than "system" so it never collides with the SQL keyword.';

COMMENT ON COLUMN system_neutron.cube_id IS
'Boxel cube identifier from the procedural name, carried from system_known. Redundant once system_in_sector is stored, but it is what boxel-level joins need.';

COMMENT ON COLUMN system_neutron.mass_code IS
'Size class of the generator cube, ''a'' to ''h'', carried from system_known. Worth reading even though this table is not about prediction: the project''s notes record that g and h neutrons are never the arrival star, so the distribution here should be concentrated in the lower codes -- the builder prints it every run so that stays visible rather than assumed.';

COMMENT ON COLUMN system_neutron.sub_cube_id IS
'Sub-cube index within the boxel, carried from system_known. Present for layout parity; nothing in the neutron use case reads it.';

COMMENT ON COLUMN system_neutron.boxel_index IS
'Index of the system within its boxel, carried from system_known. Present for layout parity; nothing in the neutron use case reads it.';

COMMENT ON COLUMN system_neutron.region_id IS
'FOREIGN KEY to region, carried from system_known -- one of the game''s 42 hand-drawn galactic regions. Nullable by declaration, populated on every row in practice.';

COMMENT ON COLUMN system_neutron.primary_star_body_id IS
'FOREIGN KEY to body: the primary star''s TYPE. *** THIS IS THE COLUMN THE TABLE IS BUILT ON, and it is the same value on every row *** -- the body_id of ''Neutron Star'' -- because membership here is exactly primary_star_body_id = that id in system_known. Kept rather than dropped so the layout matches system_known column for column; it carries no information within this table. In system_known it is NULL on 62.4% of rows, which is why this table is a floor and not a census.';

COMMENT ON COLUMN system_neutron.body_count IS
'How many bodies the system is reported to hold, carried from system_known. NULL where nobody has scanned past the primary -- common here, since a commander who stops for a jet cone boost has no reason to honk anything else.';

COMMENT ON COLUMN system_neutron.x IS
'Galactic x in light-years, EXACT -- a scanned system with reported coordinates, never a boxel centroid, so a distance computed from it needs no "~" caveat.';

COMMENT ON COLUMN system_neutron.y IS
'Galactic y in light-years, exact -- see system_neutron.x.';

COMMENT ON COLUMN system_neutron.z IS
'Galactic z in light-years, exact -- see system_neutron.x.';

COMMENT ON COLUMN system_neutron.id_poi IS
'FOREIGN KEY to poi, carried from system_known: a named point of interest attributed to this SYSTEM. Almost always NULL. A POI pinned to a named body is recorded against the body in system_body and will not appear here.';

COMMENT ON COLUMN system_neutron.id64 IS
'The game''s own 64-bit system address, carried from system_known. A join key to carrier and to any external catalogue. No UNIQUE constraint, because system_known has 96 id64 values sitting on two rows each and this inherits them.';

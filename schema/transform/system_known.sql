CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.system_known;
DROP TABLE IF EXISTS transform.system_known_source;

CREATE TABLE transform.system_known_source (
    system_id            BIGINT  NOT NULL,
    sector_name          VARCHAR,
    is_proc              BOOLEAN NOT NULL,
    sector_id            BIGINT,
    system_in_sector     VARCHAR NOT NULL,
    cube_id              VARCHAR,
    mass_code            VARCHAR,
    sub_cube_id          INTEGER,
    boxel_index          INTEGER,
    region_id            BIGINT,
    primary_star_body_id INTEGER,
    body_count           INTEGER,
    x                    DOUBLE  NOT NULL,
    y                    DOUBLE  NOT NULL,
    z                    DOUBLE  NOT NULL,
    source               VARCHAR NOT NULL
);

CREATE TABLE transform.system_known (
    system_id            BIGINT  NOT NULL,
    sector_id            BIGINT  NOT NULL,
    system_in_sector     VARCHAR NOT NULL CHECK (trim(system_in_sector) <> ''),
    cube_id              VARCHAR,
    mass_code            VARCHAR,
    sub_cube_id          INTEGER,
    boxel_index          INTEGER,
    region_id            BIGINT,
    primary_star_body_id INTEGER,
    body_count           INTEGER,
    x                    DOUBLE  NOT NULL,
    y                    DOUBLE  NOT NULL,
    z                    DOUBLE  NOT NULL,
    source               VARCHAR NOT NULL
);

COMMENT ON TABLE transform.system_known_source IS
'TRANSFORM work table: every staged system after the three feeds are merged and the name decomposed, BEFORE the sector is required. Rebuilt on every load; nothing outside this load reads it.

*** FILLED ONE BUCKET AT A TIME, by etl/system_known/transform.sql. *** The three feeds are 292M rows together, and reducing them to one row per system in a single statement needs a hash table over 200M groups -- a full-catalogue run was killed by the operating system for exactly that. Bucketing on hash(system_id) keeps each pass to a few million groups -- HASHED, not the id itself: an id64 packs the mass code in its low bits, so a plain modulo sorts systems by mass code and the buckets come out wildly uneven. Same reason the merge buckets, and the two bucket counts are independent.

It also exists so a system whose sector is not in main.sector can be COUNTED rather than vanish. transform.system_known takes the rows where sector_id resolved; etl/system_known/skipped.sql reads the rest, and they are systems waiting for etl/sector/refresh.py, not bad data.

sector_id is NULL here for exactly those rows, and 0 -- the crafted sentinel -- for a hand-named system, which is why the two cases cannot be confused. NO PRIMARY KEY: the buckets append, and a key would be rebuilt on every one of them.';

COMMENT ON COLUMN transform.system_known_source.system_id IS
'The game''s id64, or a negative name hash where no feed supplies one. See transform.system_known.system_id.';
COMMENT ON COLUMN transform.system_known_source.sector_name IS
'The sector prefix as parsed out of the name, BEFORE clean_sector_name(). Kept only so skipped.sql can say which sectors are missing.';
COMMENT ON COLUMN transform.system_known_source.is_proc IS
'TRUE when the name matched the procedural pattern. Distinguishes "hand-named, sector_id 0" from "procedural, sector not found" -- which would otherwise both look like a missing sector.';
COMMENT ON COLUMN transform.system_known_source.sector_id IS
'main.sector.sector_id, 0 for a hand-named system, and NULL when a procedural name''s sector is not in main.sector yet. That NULL is the whole point of this table.';
COMMENT ON COLUMN transform.system_known_source.system_in_sector IS
'Name with the sector prefix removed, or the whole name for a hand-named system.';
COMMENT ON COLUMN transform.system_known_source.cube_id IS
'Letter triple from the procedural name, hyphen included. NULL for a hand-named system.';
COMMENT ON COLUMN transform.system_known_source.mass_code IS
'Mass code letter a-h from the procedural name. NULL for a hand-named system.';
COMMENT ON COLUMN transform.system_known_source.sub_cube_id IS
'The number before the dash, 0 when the name has no dash. NULL for a hand-named system.';
COMMENT ON COLUMN transform.system_known_source.boxel_index IS
'The number after the dash, or the only number when there is none. NULL for a hand-named system.';
COMMENT ON COLUMN transform.system_known_source.region_id IS
'EDAstro''s per-system region label where it has one, otherwise the sector''s region. NULL is filled by nearest neighbour in etl/system_known/load.py.';
COMMENT ON COLUMN transform.system_known_source.primary_star_body_id IS
'main.body.body_id of the arrival star, from staging.primary_star or from EDAstro''s main_star_type.';
COMMENT ON COLUMN transform.system_known_source.body_count IS
'Spansh''s DECLARED count where the staged window carries it, EDAstro''s known count otherwise. NULL is not zero.';
COMMENT ON COLUMN transform.system_known_source.x IS
'X in ly, Sol-relative, from the highest-priority feed carrying the system.';
COMMENT ON COLUMN transform.system_known_source.y IS 'Y in ly, Sol-relative. See x.';
COMMENT ON COLUMN transform.system_known_source.z IS 'Z in ly, Sol-relative. See x.';
COMMENT ON COLUMN transform.system_known_source.source IS
'Which feed won the name and coordinates: spansh, edsm, edastro -- or model, for a row a migration carried across rather than read from a feed.';

COMMENT ON TABLE transform.system_known IS
'TRANSFORM: staging.spansh_system, staging.edsm_star_system and staging.edastro_star_system reduced to one row per SYSTEM, shaped exactly as main.system_known merges it. Rebuilt from staging on every load -- derived, never edited, and safe to drop.

*** IT IS ONLY AS WIDE AS THE WINDOW THAT WAS STAGED. *** A 1-day stage makes this a 1-day table. It is therefore never a census of anything: rows main.system_known holds and this does not are systems that did not CHANGE, not systems that stopped existing, which is why etl/system_known/orphans.sql is only meaningful after a full stage.

Its constraints are the input validation: system_id NOT NULL, coordinates NOT NULL, a non-blank name. Bad input fails HERE rather than in main.

*** NO PRIMARY KEY, DELIBERATELY. *** Nothing here would use one. The only thing that reads this table is the merge, which matches it against main.system_known in batches -- a HASH join, which builds its own hash table and would not probe an index even if one existed. So the key buys no lookup and costs a full ART index over 197.7M rows: declaring it made DuckDB build that index and commit it in a single transaction, which died with "failed to pin block of size 256.0 KiB (7.4 GiB/7.4 GiB used)" -- the wall schema/system_body.sql records at 570M rows, reached earlier here because the whole table commits at once.

Uniqueness still holds, STRUCTURALLY: the buckets partition system_id so no id can appear in two of them, and within a bucket the rows are a GROUP BY system_id. main.system_known does declare the key, because there it is the identity of a row that other tables point at, and its merge builds that index 64 buckets at a time.

*** (sector_id, system_in_sector) IS DELIBERATELY NOT UNIQUE. *** 1,477 name/sector pairs sit on more than one system_id, 3,349 rows in all, and EVERY ONE is a hand-named system at sector_id = 0 -- zero duplicated pairs exist in a real sector. So this is Frontier''s doing and not ours: they shipped the same catalogue designation as several distinct systems ("NGC 2168 SB 746" is five different stars), and at sector_id = 0 nothing is composed, the name is passed through verbatim. Under the old name-keyed load those collapsed into one row and the other systems were lost. The id is unique; the name is not, and asserting otherwise would throw real systems away.

THE THREE SOURCES ARE MERGED, NOT CONCATENATED. Where one system_id appears in more than one feed, the name and coordinates come from the highest-priority source that has it (spansh, then edsm, then edastro), while body_count, region_id and the arrival star are each taken from the highest-priority source whose value is NOT NULL -- so EDAstro contributes its region label and arrival-star type to a system whose coordinates came from Spansh. The pick is a min_by over a composite ordering key, NOT a window function: ranking needs a sort of every input row, and this needs only a hash aggregate.

PROCEDURAL SYSTEMS WHOSE SECTOR IS NOT IN main.sector ARE DROPPED. They are not bad rows, they are rows waiting for etl/sector/refresh.py, and etl/system_known/skipped.sql counts them so the load reports rather than hides them.';

COMMENT ON COLUMN transform.system_known.system_id IS
'THE GAME''S OWN id64, taken as given -- never allocated here and never a sequence number. Computed by the system_id() macro, which falls back to a NEGATIVE hash of the cleaned name for a system no feed gives an id64 for, exactly as sector_id() does for a hand-authored sector. The sign of this column therefore says whether the id is the game''s or ours, and the two spaces cannot collide because a real id64 is positive.';

COMMENT ON COLUMN transform.system_known.sector_id IS
'FK -> main.sector.sector_id, resolved by NAME through clean_sector_name(). 0 -- the ''crafted'' sentinel -- for a hand-named system, never NULL, because a row whose sector did not resolve does not reach this table at all.';

COMMENT ON COLUMN transform.system_known.system_in_sector IS
'The name with the sector prefix REMOVED, or the whole name for a hand-named system. NOT unique within sector_id -- see the table comment: 1,477 pairs are distinct systems sharing a catalogue designation Frontier issued more than once, and only system_id separates them.';

COMMENT ON COLUMN transform.system_known.cube_id IS
'Letter triple from the procedural name, hyphen included. NULL for a hand-named system.';

COMMENT ON COLUMN transform.system_known.mass_code IS
'Mass code letter a-h from the procedural name. NULL for a hand-named system.';

COMMENT ON COLUMN transform.system_known.sub_cube_id IS
'The number before the dash, and ZERO rather than NULL when the name has no dash -- the game reading, matching main.system_known. NULL only for a hand-named system.';

COMMENT ON COLUMN transform.system_known.boxel_index IS
'The number after the dash, or the only number when there is none. NULL only for a hand-named system.';

COMMENT ON COLUMN transform.system_known.region_id IS
'FK -> main.region.region_id. EDAstro''s own per-system label where it has one, otherwise the sector''s region. NULL where neither applies, which is a hand-named system EDAstro has not reported -- etl/system_known/load.py fills those by nearest neighbour before merging, so a NULL here is not a NULL in main.';

COMMENT ON COLUMN transform.system_known.primary_star_body_id IS
'FK -> main.body.body_id for the ARRIVAL star only, from staging.primary_star where the staged window carries it and from EDAstro''s main_star_type otherwise. Resolved against body.type = ''star'' only, because nothing in main.system_known''s DDL would stop a planet id being written here. NOT a statement about what else the system contains.';

COMMENT ON COLUMN transform.system_known.body_count IS
'Spansh''s DECLARED body count where the staged window carries it, EDAstro''s known count otherwise. NULL means not yet known and MUST NOT be read as zero.';

COMMENT ON COLUMN transform.system_known.x IS
'X in ly, Sol-relative, from the highest-priority source carrying the system. NOT NULL: a system without coordinates is not staged at all.';

COMMENT ON COLUMN transform.system_known.y IS 'Y in ly, Sol-relative. See x.';
COMMENT ON COLUMN transform.system_known.z IS 'Z in ly, Sol-relative. See x.';

COMMENT ON COLUMN transform.system_known.source IS
'Which feed supplied the name and coordinates -- spansh, edsm, edastro, or model for a row a migration carried across. A PROVENANCE column for the load report, not merged into main: it says where this row was won, not everything that contributed to it.';

-- system_known: every system we know exists. Load order tier 2
-- (needs sector, region, body, poi).
CREATE TABLE IF NOT EXISTS system_known (
    system_id   BIGINT  NOT NULL,
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
    first_seen  TIMESTAMP NOT NULL
);


-- --------------------------------------------------------------------------
-- COMMENTS. Kept in this file, beside the DDL they describe, so a schema change
-- and its documentation cannot drift apart. Re-applied by the builder after every
-- merge via common.db.apply_comment_file(), because a migration is the one thing
-- that silently drops a comment.
-- --------------------------------------------------------------------------

-- Canonical COMMENT text for `system_known`: table plus EVERY column.
-- ETL.md requires a comment on every column of every table we own. Edit here only;
-- etl/system_known/load.py re-asserts this, because a schema change silently drops
-- comments.

COMMENT ON TABLE system_known IS
'All KNOWN systems -- observed, NOT predicted. The counterpart to the prediction pool:
nothing here is inferred, every row is a system somebody has actually reported. Merged
by etl/system_known/refresh.py.

*** GRAIN: ONE ROW PER SYSTEM. *** Not per star. The only star described is the system''s
ARRIVAL star, via primary_star_body_id; there is deliberately no per-star row and no
per-star body_id. Expected size ~75M (systems with body data) rather than the 132M
individual stars in spansh_body.

The full system name is sector.sector || '' '' || system_in_sector: sector_id -> ''Blae Hypue''
plus system = ''EW-W f1-3'' gives ''Blae Hypue EW-W f1-3''. The four decomposition
columns (cube_id, mass_code, sub_cube_id, boxel_index) are redundant for naming once
system_in_sector is stored, but they are what boxel-level joins need, so they are kept.

KEYS. system_id IS THE GAME''S id64 and it is the ONLY key -- see its column comment.
*** NOTHING IN THE DATABASE ENFORCES IT. *** There is no PRIMARY KEY and no unique index: a
unique index over 200.8M rows needs more memory than this machine can give a load, so
uniqueness is held by etl/system_known/load.sql, which merges on system_id and never
inserts a row whose id is already present. A lookup by system_id is a scan.
*** (sector_id, system_in_sector) IS NOT UNIQUE. *** The name is a property of a system,
not its identity. 1,477 name/sector pairs sit on more than one system, 3,349 rows in all,
and every one is a hand-named system at sector_id = 0 -- Frontier shipped the same
catalogue designation as several distinct stars, and "NGC 2168 SB 746" is five of them.
There are ZERO duplicated pairs in a real sector. Separately, 96 id64 values used to sit
on two rows each under two SPELLINGS of one name. Keying on the name lost the first kind
and duplicated the second; keying on the id loses neither, at the price of a name lookup
being able to return more than one row. Callers that look a system up by name must
handle that.
sector_id is NOT NULL, which is what sector''s sentinel row is for: hand-named systems
(Sol, Colonia) have no sector and point at sector_id = 0 (''crafted'') rather than NULL.

REFERENCES sector, region, body and poi, all NULLABLE by design -- see each column.
*** NO FOREIGN KEY CONSTRAINT ENFORCES ANY OF THEM. *** This database declares none, so a
dangling id is possible and only common.db.check_references will tell you. Ids are still
never renumbered and never reused (ETL.md).';

COMMENT ON COLUMN system_known.system_id IS
'THE GAME''S OWN id64, used directly as the key (unenforced -- see the table comment). NOT a surrogate and NOT a
sequence number this project allocates -- every source dump carries it, so allocating
one of our own only ever created a mapping that had to be kept alive and joined through.
Computed by the system_id() macro, which takes the id64 when a feed supplies one.
*** A NEGATIVE VALUE IS OURS, NOT THE GAME''S. *** For a system no feed gives an id64
for, system_id_from_name() hashes the cleaned name to 32 bits and negates it, exactly as
sector_id() does for a hand-authored sector. A real id64 is positive, so the two spaces
cannot collide, and the SIGN of this column is what says which kind of id you are
holding.
Never renumbered and never reused: system_body, system_catalog, system_phenomenon,
carrier and system_poi all key to it, and nothing in the database would stop a
renumbering from orphaning them (ETL.md). Merges match on it directly -- there is no
longer a natural key to match on instead, because this IS the natural key.';

COMMENT ON COLUMN system_known.sector_id IS
'FK -> sector.sector_id. NOT NULL. The 151,446 hand-named systems (Sol, Colonia, ~0.1%)
carry no sector in their name and point at the SENTINEL sector_id = 0 (''crafted'')
rather than NULL -- system_id is the key and sector_id is NOT NULL beside it. For
those rows cube_id / mass_code / sub_cube_id / boxel_index are all NULL, since there is no
procedural name to decompose, and system_in_sector holds the entire name instead.
Filter sector_id <> 0 when you mean an actual sector.';

COMMENT ON COLUMN system_known.system_in_sector IS
'The system name WITHOUT the sector, e.g. ''EW-W f1-3'' for ''Blae Hypue EW-W f1-3''.
The full name is sector.sector || '' '' || system_in_sector, so this plus sector_id rebuilds it
exactly without repeating the sector prefix 75M times.
For the 151,446 HAND-NAMED systems there is no sector, so this holds the WHOLE name --
''Sol'', ''Colonia'', ''Sagittarius A*''. That is what makes every row identifiable;
the decomposition columns alone cannot do it for those systems.
system_in_sector is a NAME fragment -- do not confuse it with system_id (the game''s id64)
or boxel_index (the integer index within a boxel). NOT NULL, but NOT unique even within a
sector: see the table comment.';

COMMENT ON COLUMN system_known.region_id IS
'FK -> region.region_id, one of the 42 hand-drawn galactic regions. NULLABLE because
region is NOT derivable from a name or coordinate by formula. It comes from the system''s
sector where the name has one, from EDAstro''s own per-system label where that feed
carries the system, and from a nearest-neighbour vote in etl/system_known/load.py for the
hand-named systems neither covers. NULL means unclassified, not regionless.';

COMMENT ON COLUMN system_known.primary_star_body_id IS
'FK -> body.body_id: the type of the system''s PRIMARY (arrival) star -- the one you drop
out of witchspace beside. This is the ONLY star this table describes, since the grain is
one row per system. Join body.code to match live journal StarType values, body.body to
match the dumps'' sub_type strings.
NULLABLE when the system is unscanned or the arrival star untyped. NOTE nothing in the
DDL restricts this to star rows -- body also holds the 19 planet types -- so the loader
must enforce body.type = ''star'' itself; a planet body_id here would be accepted.
GOTCHA carried over from the neutron work: in g/h-mass systems the neutron star is NEVER
the arrival star, so filtering on this column is NOT the same as asking whether a system
contains a given class. The same caution applies to black holes and Wolf-Rayets.';

COMMENT ON COLUMN system_known.body_count IS
'Number of bodies in the system. NULL when not yet known -- an unhonked system reports
nothing, and NULL MUST NOT be read as zero.
BEWARE which count this is when populating. The game DECLARES a body count at the honk
(staging.spansh_system.declared_body_count) and that is the trustworthy figure: it is the system''s own
assertion of what exists, known even for systems nobody finished scanning. It is NOT the
number of bodies we HOLD -- across systems with both we hold 250,310,973 of 324,801,067
declared bodies (77.1%), and 21.9% of honked systems are still partial. So
declared_body_count >= count of matching spansh_body rows, and the gap is real data we do
not have rather than an error.';

COMMENT ON COLUMN system_known.cube_id IS
'The letter triple from the procedural name, e.g. ''EW-W'' in ''Blae Hypue EW-W f1-3''.
Stored with the hyphen, exactly as it appears. With sector it identifies the cube; with
mass_code and sub_cube_id it identifies the boxel.';

COMMENT ON COLUMN system_known.mass_code IS
'Single letter a-h from the procedural name, e.g. ''f'' in ''Blae Hypue EW-W f1-3''.
A HARD Stellar Forge gate, not a label: black holes occur only in e/f/g/h and Wolf-Rayet
only in h, which is why the prediction engine keys on it. Later letters mean larger,
rarer boxels -- an h boxel is the whole 1280-ly sector, an a boxel is 10 ly.';

COMMENT ON COLUMN system_known.sub_cube_id IS
'The number BEFORE the dash in the procedural name -- 1 in ''Blae Hypue EW-W f1-3''.
*** ZERO, NOT NULL, WHEN THE NAME HAS NO DASH. *** 10,874,986 systems (5.6%) carry a
single number, e.g. ''Iwaith CL-Y g226'', ''Eephonth AA-A h0''. We use the GAME
READING: that number is the SYSTEM INDEX and the sub-cube part is implicitly 0, so
''g226'' means sub_cube_id = 0 and boxel_index = 226 -- NOT sub_cube_id = 226.
The positional alternative was considered and REJECTED: a per-boxel rollup keyed on
and etl/sector/build.py all build the boxel key as coalesce(<part>, ''0''), so reading
it positionally would have disagreed with the boxel model on 10.9M systems and broken
every join on boxel identity.
NULL only for hand-named systems, which have no procedural name at all.';

COMMENT ON COLUMN system_known.boxel_index IS
'The index of the system within its BOXEL: 3 in ''Blae Hypue EW-W f1-3''. Under the game
reading this is the number AFTER the dash, or the ONLY number when there is no dash --
''Iwaith CL-Y g226'' gives boxel_index = 226 with sub_cube_id = 0. NEVER NULL for a
procedural name; NULL means a hand-named system.
*** NOT AN IDENTIFIER. *** It is unique only within (sector_id, cube_id, mass_code,
sub_cube_id), and it is not system_id -- the id64 packs the boxel address differently and
the two are unrelated as numbers.
The index is generation ORDER, so it is dense from 0 and an internal gap means a system
that exists but has not been catalogued -- exactly what the boxel-gap layer in
system_predicted enumerates.';

COMMENT ON COLUMN system_known.x IS
'X coordinate in ly, Sol-relative, matching staging.spansh_system.';

COMMENT ON COLUMN system_known.y IS
'Y coordinate in ly, Sol-relative. y is galactic HEIGHT in this coordinate system, so it
has a far narrower range than x and z.';

COMMENT ON COLUMN system_known.z IS
'Z coordinate in ly, Sol-relative. Sgr A* sits at roughly (25.2, -20.9, 25899), so large
positive z is coreward.';

COMMENT ON COLUMN system_known.first_seen IS
'WALL-CLOCK TIME THIS ROW WAS INSERTED, one instant per load rather than one per row, so
every system a run adds carries the same value. Set on INSERT ONLY -- the merge''s update
arm never touches it, which is what keeps it meaning "first seen" rather than "last
touched". Local time, matching the journal.
*** THIS IS WHAT DECIDES WHICH DUMP TO DOWNLOAD. *** max(first_seen) against now() is how
far behind the model is, and etl/system_known/stage.py asks each provider for the
narrowest window it publishes that spans that gap. A load that inserts nothing leaves the
value where it is and the next run therefore asks for a WIDER dump, which is the safe
direction: a window narrower than the gap leaves a hole no later delta reaches back to.
It is NOT a discovery date. It says when this project first recorded the system, not when
a commander found it -- a system Spansh has carried for years gets today''s timestamp if
today is when we merged it.';

COMMENT ON COLUMN system_known.id_poi IS
'REFERENCES poi.poi_id: the SYSTEM-LEVEL point of interest catalogued here, NULL for the overwhelming majority. UNENFORCED, like every reference in this database -- the --poi phase validates it in SQL after writing, and common.db.check_references covers it too. Only POIs the catalogue does NOT pin to a named body land here; anything with a body goes to system_body.id_poi, so the two never double-count. ONE column, but 32,058 systems hold more than one POI family: the RAREST POI wins (ties break on poi_id, deterministically), because the rare thing is why you would fly there. The full multi-POI truth is in system_phenomenon, keyed (system_id, phenomenon) precisely so it can hold all of them. *** NEVER read a non-NULL id_poi as "already taken" *** -- a POI is credited to YOU however many commanders logged it first, which is the whole reason POIs are tracked separately from predicted targets.';

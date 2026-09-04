-- system_known: every system we know exists. Load order tier 2
-- (needs sector, region, body, poi).
CREATE TABLE IF NOT EXISTS system_known (
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
    -- NO UNIQUE constraint: 96 id64 values map to two rows each, the same system
    -- recorded under two name spellings. A real defect this column exposed, not id64
    -- reuse -- fix the duplicates, then add the key.
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

-- Canonical COMMENT text for `system_known`: table plus EVERY column.
-- ETL.md requires a comment on every column of every table we own. Edit here only;
-- etl/build_system_known.py re-asserts this, because a schema change silently drops
-- comments.

COMMENT ON TABLE system_known IS
'All KNOWN systems -- observed, NOT predicted. The counterpart to the prediction pool:
nothing here is inferred, every row is a system somebody has actually reported. Created
by etl/build_system_known.py.

*** GRAIN: ONE ROW PER SYSTEM. *** Not per star. The only star described is the system''s
ARRIVAL star, via primary_star_body_id; there is deliberately no per-star row and no
per-star body_id. Expected size ~75M (systems with body data) rather than the 132M
individual stars in spansh_body.

*** NOT POPULATED YET (DDL created 2026-08-11). *** The DDL exists so foreign keys can be
declared -- DuckDB has no ALTER TABLE ADD FOREIGN KEY, so they must be present at CREATE
and adding one later means rebuilding the table.

The full system name is sector.sector || '' '' || system_in_sector: sector_id -> ''Blae Hypue''
plus system = ''EW-W f1-3'' gives ''Blae Hypue EW-W f1-3''. The four decomposition
columns (cube_id, mass_code, sub_cube_id, boxel_index) are redundant for naming once
system_in_sector is stored, but they are what boxel-level joins need, so they are kept.

KEYS. system_id is a SURROGATE BIGINT PRIMARY KEY: our own sequence number, NOT the
game''s id64 and not derived from anything. The natural key (sector_id, system_in_sector) is
declared UNIQUE beside it, so both are enforced -- merges match on the natural key and
must never renumber system_id (ETL.md).
Both key columns are NOT NULL, which is exactly what sector''s sentinel row is for:
hand-named systems (Sol, Colonia) have no sector and point at sector_id = 0
(''crafted'') rather than NULL, because a NULL cannot participate in a UNIQUE or
PRIMARY KEY.

FOREIGN KEYS to sector, region and body, all NULLABLE by design -- see each column.
DuckDB ENFORCES them, so bulk loading is slower than into an unconstrained table and rows
in the parent tables cannot be deleted while referenced. That is the intended protection
(ETL.md: ids are never renumbered or reused).';

COMMENT ON COLUMN system_known.system_id IS
'SURROGATE PRIMARY KEY: our own BIGINT sequence number. NOT the game''s id64, NOT derived
from the name, and NOT the boxel index -- that is `boxel_index`. Nothing about a system
can be inferred from this value.
Allocated max+1 for genuinely new systems and NEVER renumbered, because other tables key
to it and DuckDB silently drops inbound foreign keys on a CREATE OR REPLACE (ETL.md).
Merges must match on the natural key (sector_id, system_in_sector), never on this.';

COMMENT ON COLUMN system_known.sector_id IS
'FK -> sector.sector_id. NOT NULL. The 151,446 hand-named systems (Sol, Colonia, ~0.1%)
carry no sector in their name and point at the SENTINEL sector_id = 0 (''crafted'')
rather than NULL -- a NULL cannot take part in the UNIQUE (sector_id, system_in_sector) key. For
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
system_in_sector is a NAME fragment -- do not confuse it with system_id (the surrogate primary
key) or boxel_index (the integer index within a boxel). NOT NULL, and together with
sector_id it forms the UNIQUE natural key.';

COMMENT ON COLUMN system_known.region_id IS
'FK -> region.region_id, one of the 42 hand-drawn galactic regions. NULLABLE because
region is NOT derivable from a name or coordinate by formula -- it needs a
nearest-neighbour lookup against the 545,485 labelled points in input/region.parquet
(99.55% accurate on hold-out). NULL means unclassified, not regionless.';

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
and etl/build_sector.py all build the boxel key as coalesce(<part>, ''0''), so reading
it positionally would have disagreed with the boxel model on 10.9M systems and broken
every join on boxel identity.
NULL only for hand-named systems, which have no procedural name at all.';

COMMENT ON COLUMN system_known.boxel_index IS
'The index of the system within its BOXEL: 3 in ''Blae Hypue EW-W f1-3''. Under the game
reading this is the number AFTER the dash, or the ONLY number when there is no dash --
''Iwaith CL-Y g226'' gives boxel_index = 226 with sub_cube_id = 0. NEVER NULL for a
procedural name; NULL means a hand-named system.
*** NOT AN IDENTIFIER. *** It is unique only within (sector_id, cube_id, mass_code,
sub_cube_id), and is neither the surrogate key (system_id) nor the game''s id64 -- the
three are unrelated.
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

COMMENT ON COLUMN system_known.id_poi IS
'FK to poi(poi_id): the SYSTEM-LEVEL point of interest catalogued here, NULL for the overwhelming majority. *** THE FOREIGN KEY IS UNENFORCED ON ANY DATABASE THAT PREDATES THE COLUMN *** -- DuckDB has no ALTER TABLE ADD CONSTRAINT, so the FK in build_system_known.py''s CREATE binds only on a fresh build; the --poi phase validates it in SQL after writing instead. Only POIs the catalogue does NOT pin to a named body land here; anything with a body goes to system_body.id_poi, so the two never double-count. ONE column, but 32,058 systems hold more than one POI family: the RAREST POI wins (ties break on poi_id, deterministically), because the rare thing is why you would fly there. The full multi-POI truth is in system_phenomenon, keyed (system_id, phenomenon) precisely so it can hold all of them. *** NEVER read a non-NULL id_poi as "already taken" *** -- a POI is credited to YOU however many commanders logged it first, which is the whole reason POIs are tracked separately from predicted targets.';

COMMENT ON COLUMN system_known.id64 IS
'The GAME''s own 64-bit system id, carried from the source dumps. This is the ONLY reliable join between system_known and any raw dump or catalogue -- names are not, because sector.is_crafted is TRUE for 424 real named sectors and concatenating sector to build a full name silently fabricates millions of phantom "missing" systems (see ETL.md). Before this column existed the mapping lived ONLY in staging.sys_bridge, which made a transient staging table load-bearing. *** NOT UNIQUE IN THIS TABLE, though it is unique in the game: 96 id64 values sit on two rows each -- the same system recorded under two name spellings ("CoRoT-9"/"Corot-9", "h2 Puppis"/"H2 Puppis", "Eskimo Sector VE-P b6-0"/"NGC 2392 Sector VE-P b6-0"). Those 192 rows are a duplicate-system defect this column EXPOSED, not id64 reuse; de-duplicate them and the UNIQUE key can then be declared on a fresh build. *** NULL on 3 rows that appear in no dump carrying an id64.';

-- sector: one row per unique sector with a rough bounding ball. Load order tier 1.
-- GOTCHA: is_crafted is TRUE for 424 REAL named sectors, not just the sector_id=0
-- sentinel. Only sector_id=0 means a system's name stands alone. See ETL.md.
CREATE TABLE IF NOT EXISTS sector (
    sector_id  BIGINT  NOT NULL PRIMARY KEY,
    sector     VARCHAR NOT NULL UNIQUE,
    x          DOUBLE  NOT NULL,
    y          DOUBLE  NOT NULL,
    z          DOUBLE  NOT NULL,
    radius     DOUBLE  NOT NULL,
    is_crafted BOOLEAN NOT NULL,
    region_id  BIGINT
);

-- --------------------------------------------------------------------------
-- COMMENTS. Kept in this file, beside the DDL they describe, so a schema change
-- and its documentation cannot drift apart. Re-applied by the builder after every
-- merge via common.db.apply_comment_file(), because a migration is the one thing
-- that silently drops a comment.
-- --------------------------------------------------------------------------

-- Canonical COMMENT text for `sector`: the table comment plus EVERY column.
-- ETL.md requires a comment on every column of every table we own. Edit here only;
-- etl/sector/build.py re-asserts this file after each merge, because a schema
-- change is the one thing that silently drops comments.

COMMENT ON TABLE sector IS
'One row per unique SECTOR with a rough bounding ball, DERIVED from system_known by
etl/sector/build.py. 12,064 sectors: 11,641 procedural + 423 hand-crafted.

Sector names are parsed by stripping the '' AB-C d1-234'' suffix from procedural
system names, so HAND-AUTHORED SYSTEMS (Sol, Colonia, every named star) are ABSENT
-- they carry no sector in their name. Note that is separate from is_crafted, which
is about hand-crafted SECTORS and is populated here.

GEOMETRY CHECKS, both reassuring. (1) A single 1280-ly cell has a maximum taxicab
half-extent of 1920 and NOT ONE of the 12,064 sectors exceeds it -- largest is 1918.6
(Juenae) -- so every sector name fits inside one cell. (2) 8,896 of 12,064 centres
land exactly on a 1280-ly cell mid-plane in x, which is what should happen once a
sector is sampled to its corners. Together these confirm the lattice (1280 ly, origin
-49985,-40985,-24105) from sector geometry alone, independently of the boxel work.

*** sector_id = 0 IS A SENTINEL, NOT A SECTOR. *** It has sector = ''crafted'' and
x = y = z = radius = 0. It exists so hand-named systems (Sol, Colonia, every named star),
which carry no sector in their name, have something to point at:
system_known.sector_id is NOT NULL and uses 0 for those, because a NULL cannot take part
in a UNIQUE or PRIMARY KEY. EXCLUDE sector_id = 0 from any analysis of real sectors -- it
is flagged is_crafted = true, so without that filter it inflates the crafted count from
423 to 424 and drags the crafted mean radius toward zero. The builder''s own diagnostics
all filter it out.

Merged on the natural key `sector`, never dropped (ETL.md). x/y/z/radius move as
coverage grows so matched rows ARE updated; only sector_id is immutable. The sentinel is
upserted separately and is exempt from orphan reporting, since it can never appear in the
set derived from procedural system names.';

COMMENT ON COLUMN sector.sector_id IS
'BIGINT PRIMARY KEY, and *** THE GAME''S OWN SECTOR ADDRESS, NOT A SEQUENCE WE ALLOCATE. *** Written by the sector_id() macro from the id64 grid cell EDAstro publishes: x + 128y + 16384z, giving 35,968..1,151,014 and decoding back with sid%128, (sid//128)%128, sid//16384. Two sectors cannot share one because two sectors cannot share a cell.

*** A NEGATIVE VALUE MEANS HAND-AUTHORED. *** Col 359 Sector, NGC 2546 Sector, Bleia1..5 and 429 others are named overlays on the procedural grid, not cells of it, so they have no address to pack. sector_id_from_name() hashes the cleaned name to 32 bits and negates it, which cannot collide with a packed cell because the sign differs. THE SIGN OF THIS COLUMN IS is_crafted -- the two agree on every row and are checked to.

sector_id = 0 is the SENTINEL, neither: it is the row hand-named systems (Sol, Colonia) point at, because system_known.sector_id is NOT NULL and a NULL cannot take part in a UNIQUE key.

Stability: a packed cell is permanent. A hashed id is only as stable as DuckDB''s hash(), which is not promised across versions -- existing rows are safe because they are never recomputed, but a hand-authored sector first seen after a hash change would take a different id.';

COMMENT ON COLUMN sector.sector IS
'The sector name alone, e.g. ''Blae Hypue''. The NATURAL KEY (UNIQUE) that merges
match on -- never match on sector_id. Obtained by stripping the '' AB-C d1-234''
procedural suffix from system names.';

COMMENT ON COLUMN sector.x IS
'X of the sector centre, defined as the MIDPOINT OF THE BOUNDING BOX of the systems
we know about -- deliberately NOT the centroid and NOT the lattice cell centre. See
sector.y for the full reasoning.';

COMMENT ON COLUMN sector.y IS
'Y of the sector centre (bounding-box midpoint). Chosen over two alternatives:
avg(y), which is what sector_lookup.cy holds, is a SAMPLING-BIASED centroid dragged
toward whichever corner people happened to explore -- it yields an ~8% larger mean
radius and up to 2907 ly worst case versus 1919 for the midpoint. The 1280-ly
lattice cell centre would be unbiased but is undefined for sector names whose systems
straddle a cell boundary. The midpoint is the choice that makes `radius` a tight
bounding ball.';

COMMENT ON COLUMN sector.z IS
'Z of the sector centre (bounding-box midpoint). See sector.y for the reasoning.';

COMMENT ON COLUMN sector.radius IS
'Rough sector radius: the maximum TAXICAB (L1) distance from (x,y,z) to any system we
know about in this sector. *** A LOWER BOUND ON THE TRUE EXTENT, NOT THE SECTOR SIZE.
*** A barely-explored sector reports a small radius because nobody has visited its
corners, not because it is small -- 1,108 sectors report under 500 ly while 7,716
report 1500-1920. Do not use it to compare sector sizes; use it as a containment
radius for "might this sector hold something near me".';

COMMENT ON COLUMN sector.is_crafted IS
'TRUE for HAND-CRAFTED (real-world) sectors, FALSE for procedurally generated ones.
423 of the 12,064 real sectors are crafted. NOTE the sector_id = 0 sentinel is also
is_crafted = true, so a bare count returns 424 -- add sector_id <> 0 to count real
crafted sectors. Derived purely from the name, and the rule is exhaustive:
every crafted sector ends in '' Sector'' (406 -- Witch Head Sector, NGC 2546 Sector,
Col 359 Sector, M25 Sector, ...) or '' Dark Region'' (17 -- Coalsack Dark Region,
Horsehead Dark Region, ...). Verified: no procedural name has 3+ words, and the only
9 procedural names containing a digit are far-side procgen sectors (Bleia1..5,
Praei1..4, at z 37,000-54,000 out past the disc edge, 13 systems total) which are
generated rather than crafted and are therefore FALSE.
Crafted sectors are worth flagging because their geometry behaves differently: their
member systems straddle several 1280-ly lattice cells, since a compact real cluster
sitting on a cell CORNER touches up to 8 cells. They are not oversized though --
their radii top out at 1063, well inside a single cell.';

COMMENT ON COLUMN sector.region_id IS
'Which of the 42 hand-drawn galactic regions this sector sits in -- ONE region for the
WHOLE sector. REFERENCES region.region_id, checked by common.db.check_references after
every load rather than by a constraint -- this database declares no foreign keys.

*** AN APPROXIMATION, DELIBERATELY. *** Regions are galaxy-scale and sectors are 1280 ly,
so a sector usually lies wholly inside one region -- but 15.1% of sectors with labelled
systems straddle a region boundary, and for those the single value is wrong for some of
their systems. Measured on a held-out half of EDAstro''s 545,485 labels: this
sector-level assignment scores 95.0%, against 99.4% for per-system k=5 kNN. The trade is
12,064 lookups instead of 197,562,522, and it is the reason system_known.region_id can be
a plain join instead of a spatial query.
Worst offenders are the boundary sectors: Oochost (2,323 of 13,757 labelled systems
wrong), Outopps (1,783 of 11,863), Outotz, Outorst.

Assigned from two sources, best first: (a) the MODAL region of the sector''s own labelled
member systems, which is direct evidence but exists for only about a third of sectors;
(b) k=5 majority vote around the sector CENTRE, which covers the rest. Sector centres are
bounding-box midpoints, so in a sparsely-explored sector the centre itself is approximate
and the region is correspondingly less certain.
NULL on the sector_id = 0 sentinel, which is not a place.';

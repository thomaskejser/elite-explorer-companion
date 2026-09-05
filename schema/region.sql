-- region: the 42 hand-drawn galactic regions. Load order tier 1.
-- region_id is the GAME's id, not ours: never allocated, always taken as given.
CREATE TABLE IF NOT EXISTS region (
    region_id BIGINT  NOT NULL PRIMARY KEY,
    region    VARCHAR NOT NULL UNIQUE
);

-- --------------------------------------------------------------------------
-- COMMENTS. Kept in this file, beside the DDL they describe, so a schema change
-- and its documentation cannot drift apart. Re-applied by the builder after every
-- merge via common.db.apply_comment_file(), because a migration is the one thing
-- that silently drops a comment.
-- --------------------------------------------------------------------------

-- Canonical COMMENT text for `region`: table plus EVERY column.
-- ETL.md requires a comment on every column of every table we own. Edit here only;
-- etl/region/load.py re-asserts this after each merge, because a schema change is the
-- one thing that silently drops comments.

COMMENT ON TABLE region IS
'The 42 hand-drawn GALACTIC REGIONS (Inner Orion Spur, The Abyss, Galactic Centre, ...).
Merged from input/region.parquet by etl/region/load.py; seeded once by
etl/region/build.py.

*** input/region.parquet is the ONLY source of truth and is MAINTAINED BY HAND. ***
This is the one table here with no upstream feed. Frontier draws the regions; they are
NOT derivable from a system''s name or coordinates by any formula, and they change only
when Frontier changes them. Nothing re-derives this file -- if it is wrong, edit it.

A region is NOT the same thing as a sector. There are 42 regions covering the whole
galaxy versus 12,064 sectors, and the two carve space up on completely different
schemes: sectors are the 1280-ly procedural-generation lattice, regions are hand-drawn
map areas. Neither nests inside the other.

To classify an arbitrary POINT into a region, use input/region.parquet (545,485 systems
labelled by EDAstro, keyed on these region_ids) by nearest neighbour -- there is no
formula. That method validated at 99.55% on a 20% hold-out (k=5 majority vote) and
spot-checks correctly: Sol -> Inner Orion Spur, Sgr A* -> Galactic Centre, Colonia ->
Inner Scutum-Centaurus Arm, Beagle Point -> The Abyss.

Merged, never dropped (ETL.md): matched on region_id, names updated, rows absent from
the file left in place and reported rather than deleted.';

COMMENT ON COLUMN region.region_id IS
'BIGINT PRIMARY KEY. *** THE GAME''S OWN REGION ID, NOT A SEQUENCE WE INVENTED. ***
This is the crucial difference from body.body_id and sector.sector_id, which we
allocate: region_id is parsed from the codex feed''s region_name token and is therefore
NOT ours to assign. The loader takes it from the file as given -- it never allocates
max+1 and never renumbers.
Why it matters: input/region.parquet already keys 545,485 labelled points on these ids
and the Canonn codex feed uses them, so renumbering would orphan all of it. Values run
1..42 with no gaps, but treat that as an observation rather than a guarantee -- if
Frontier adds a region it will bring its own id.';

COMMENT ON COLUMN region.region IS
'Region display name in English, e.g. ''Outer Scutum-Centaurus Arm''. UNIQUE.
Extracted as the MODAL non-null region_name_localised per id from canonn_codex_event:
that feed is uploaded by clients in every language, so a naive pick returns
''Bras Ecu-Croix externe'' rather than the English name. English is the plurality, which
is what makes the modal choice work -- it is a heuristic, not a guarantee, so a wrong
name is fixed by editing input/region.parquet rather than by re-running the seeder.
Note the apostrophes are real and load-bearing: Ryker''s Hope, Odin''s Hold,
Hawking''s Gap, Dryman''s Point, Newton''s Vault, Aquila''s Halo, Achilles''s Altar,
Kepler''s Crest, Lyra''s Song. Quote accordingly in SQL.';

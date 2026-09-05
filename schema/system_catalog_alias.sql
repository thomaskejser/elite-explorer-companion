-- system_catalog_alias: two catalogue names that are THE SAME STAR.
-- Load order tier 3 in spirit, but it has NO foreign key: both endpoints are names,
-- not ids, so it can be created by its own loader at any time.
CREATE TABLE IF NOT EXISTS system_catalog_alias (
    -- CANONICALLY ORDERED: system_a < system_b, always. The relation is symmetric, so
    -- storing both directions would double the rows and let them disagree. Consumers
    -- that need both directions UNION the reverse -- see the column comment.
    system_a  VARCHAR NOT NULL,
    system_b  VARCHAR NOT NULL,
    source    VARCHAR NOT NULL,
    PRIMARY KEY (system_a, system_b)
);

-- --------------------------------------------------------------------------
-- COMMENTS. Beside the DDL they describe, per ETL.md, and re-applied by the loader
-- after every merge because a migration is the one thing that silently drops them.
-- --------------------------------------------------------------------------

COMMENT ON TABLE system_catalog_alias IS
'CROSS-IDENTIFICATIONS between the real-world catalogues in `system_catalog`: one row per
pair of names that astronomy says are the SAME STAR. Seeded by
etl/system_catalog_alias/build.py from the cross-ID columns the catalogues themselves
publish, merged by etl/system_catalog_alias/load.py from
input/system_catalog_alias.parquet.

*** WHY IT EXISTS: A CATALOGUE NAME MISSING FROM THE GAME IS NOT A MISSING STAR. ***
Frontier ships each real star under ONE designation, and which one it picks is not the
one you happen to be looking up: measured over Hipparcos, the game names a star `HIP n`
inside ~1000 ly and `HD n` beyond it (0.1% HD below 500 ly, 49% at 1000-1100 ly, ~95%
past 2000 ly). Of 118,218 Hipparcos stars, 98,421 are in the game under exactly one of
HIP / HD / BD / CD / CPD -- and only 21 under two. So `system_catalog.system_id` resolved
by NAME ALONE answered "did Frontier use this catalogue''s spelling", when the question
worth asking is "is this star in the game at all". This table is what closes that gap:
etl/system_catalog/load.py walks these edges to a resolved neighbour and copies its
system_id, so both names point at the one system_known row.

WHAT IS AND IS NOT IN HERE. Only cross-IDs the catalogues assert about each other, and
only where BOTH endpoint names already exist in `system_catalog` -- an edge to a name we
do not hold would resolve nothing and would hide a rendering bug, since a mis-spelled
endpoint simply vanishes instead of failing. Sources, one per `source` value.

*** TWO SOURCES END AT A GAME NAME RATHER THAN A CATALOGUE NAME, AND THEY ARE THE ONLY
WAY TO REACH THE BRIGHT STARS. *** Below V=6 Frontier uses proper, Bayer and Flamsteed
names -- Sirius, Alpha Centauri, 61 Cygni -- which are not catalogue designations and can
never appear in `system_catalog`. An edge with both feet in a catalogue cannot reach them,
so these two put one foot in the game:

  bayer:IV/27A   9,399 edges. HD/HR/HIP -> the Bayer or Flamsteed name RENDERED into the
                 galaxy map''s spelling: a genitive table for all 88 constellations plus a
                 Greek-letter table turn "alf Cen" into "Alpha Centauri" and "61 Cyg" into
                 "61 Cygni". Frontier''s own misspellings are carried as alternates
                 ("Chamaelontis" for Chamaeleontis) -- the game''s spelling wins, because
                 the string has to paste into the search box.
  simbad:ident   4,313 edges. Every hand-named game system that is not a catalogue name,
                 looked up in SIMBAD as an IDENTIFIER. Deliberately prefix-agnostic: it
                 reaches survey names (Wolf 359), variable-star names and exoplanet hosts
                 without a rule for each, and returns nothing for Frontier''s ~20,000
                 invented names. Two spelling fixes are applied to what SIMBAD returns --
                 "GJ 406" is offered as "Gliese 406" (the game''s spelling, which
                 system_catalog follows) and a component letter is optionally dropped
                 ("HD 48915A" -> "HD 48915").

Together they took HR from 52% present to 87.8% and lifted the reachable ceiling from
109,458 game systems to 113,618.

A RENDERED NAME THAT IS NOT IN system_known IS DROPPED, so a wrong genitive costs a
missing edge and never a wrong one. That is the same both-endpoints-must-exist rule the
catalogue sources follow, pointed at the game instead.

NOT A TRANSITIVE CLOSURE. Edges are stored as published, one hop each. The transitive
step (TYC -> HIP -> HD -> BD) happens in the LOADER, which iterates to a fixpoint, and
refuses to propagate where a name''s resolved neighbours disagree about which system_id
they mean. Those refusals are reported, never guessed at.';

COMMENT ON COLUMN system_catalog_alias.system_a IS
'One endpoint of the identity, as a full pasteable name in GAME spelling -- the same
string space as system_catalog.system, which is what makes the join work.

*** ORDERED: system_a < system_b BY STRING COMPARISON, ALWAYS. *** The relation is
symmetric and the canonical order is what keeps the primary key from admitting the same
edge twice. To traverse, union the reverse:

    SELECT system_a AS a, system_b AS b FROM system_catalog_alias
    UNION ALL SELECT system_b, system_a FROM system_catalog_alias';

COMMENT ON COLUMN system_catalog_alias.system_b IS
'The other endpoint. Same spelling rules as system_a, and always the GREATER of the two
strings. Not a foreign key -- neither column is -- because the natural target,
system_catalog.system, is a name whose row may be inserted by a later re-seed.';

COMMENT ON COLUMN system_catalog_alias.source IS
'WHICH CATALOGUE ASSERTED THE IDENTITY, as `<VizieR table tag>:<column>`, e.g.
`hip_main:HD` or `tyc2:HIP`. Provenance, and the thing to GROUP BY when an edge looks
wrong: a cross-ID is somebody''s published claim, not a measurement we made, and the
older catalogues disagree with each other about components of multiple stars.

An identity published by two sources is stored ONCE, keeping whichever source the
builder read first -- the sources are ordered most-authoritative-first in that script.';

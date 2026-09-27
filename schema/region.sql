CREATE TABLE IF NOT EXISTS region (
    region_id BIGINT  NOT NULL PRIMARY KEY,
    region    VARCHAR NOT NULL UNIQUE
);

COMMENT ON TABLE region IS
'The 42 hand-drawn GALACTIC REGIONS (Inner Orion Spur, The Abyss, Galactic Centre, ...).

Refreshed by etl/region/refresh.py, which downloads the Canonn codex, stages it as staging.canonn_codex_event, reduces it to transform.region and MERGEs that into here. Nothing about it is hand-maintained any more.

A region is NOT the same thing as a sector. There are 42 regions covering the whole galaxy versus 12,064 sectors, and the two carve space up on completely different schemes: sectors are the 1280-ly procedural-generation lattice, regions are hand-drawn map areas. Neither nests inside the other.

Frontier draws the regions. They are NOT derivable from a system''s name or coordinates by any formula, and they change only when Frontier changes them, so this table gains a row only when the codex feed starts reporting a new region_id.

To classify an arbitrary POINT into a region there is no formula: use the systems EDAstro has already labelled (staging.edastro_star_system.region) by nearest neighbour. That method validated at 99.55% on a 20% hold-out (k=5 majority vote) and spot-checks correctly: Sol -> Inner Orion Spur, Sgr A* -> Galactic Centre, Colonia -> Inner Scutum-Centaurus Arm, Beagle Point -> The Abyss.

Merged, never dropped (ETL.md): matched on region_id, names updated, rows absent from the source left in place and reported rather than deleted.

*** ON A DATABASE THAT STILL DECLARES FOREIGN KEYS, A NAME HERE CANNOT BE UPDATED. *** system_known and system_neutron carry region_id, and where that is a real constraint DuckDB refuses to update any row it references -- by MERGE, by UPDATE, by any statement -- so the merge can insert a new region but not rename one. schema/ no longer declares those keys, which lifts the restriction on the next database built from it; a database created before that still has them.';

COMMENT ON COLUMN region.region_id IS
'BIGINT PRIMARY KEY. *** THE GAME''S OWN REGION ID, NOT A SEQUENCE WE INVENTED. ***
This is the crucial difference from body.body_id and sector.sector_id, which we allocate: region_id is parsed from the codex feed''s region_name token and is therefore NOT ours to assign. The loader takes it as given -- it never allocates max+1 and never renumbers.
Why it matters: everything labelled by region keys on these ids and the Canonn codex feed uses them, so renumbering would orphan all of it. Values run 1..42 with no gaps, but treat that as an observation rather than a guarantee -- if Frontier adds a region it will bring its own id.';

COMMENT ON COLUMN region.region IS
'Region display name in English, e.g. ''Outer Scutum-Centaurus Arm''. UNIQUE.
Extracted as the MODAL non-null region_name_localised per id by schema/transform/region.sql: the codex feed is uploaded by clients in every language, so a naive pick returns ''Bras Ecu-Croix externe'' rather than the English name. English is the plurality, which is what makes the modal choice work -- it is a heuristic, not a guarantee.
Note the apostrophes are real and load-bearing: Ryker''s Hope, Odin''s Hold, Hawking''s Gap, Dryman''s Point, Newton''s Vault, Aquila''s Halo, Achilles''s Altar, Kepler''s Crest, Lyra''s Song. Quote accordingly in SQL.';

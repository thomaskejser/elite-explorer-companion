CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.system_body;

CREATE TABLE transform.system_body (
    system_id        BIGINT  NOT NULL,
    body_no          INTEGER NOT NULL,
    system_body      VARCHAR NOT NULL,
    body_name        VARCHAR NOT NULL,
    body_id          INTEGER,
    is_primary       BOOLEAN NOT NULL,
    discovered_time  TIMESTAMP,
    solar_masses     DOUBLE,
    earth_masses     DOUBLE,
    is_terraformable BOOLEAN,
    source           VARCHAR NOT NULL
);

COMMENT ON TABLE transform.system_body IS
'TRANSFORM: every staged body feed shaped exactly as main.system_body merges it, keyed (system_id, system_body, body_no). Created empty on each load and filled one system_id bucket at a time by etl/system_body/transform.sql, each bucket merged before the next is filled. Derived, never edited, safe to drop.

SOURCES, highest priority first: spansh (the staged window), edsm (7-day), edastro (7-day planets), edastro_neutron and edastro_rare (full catalogues, CATALOGUE-ONLY). A body reported by several feeds takes its row from the highest; masses and the terraformable flag are the largest reported by any.

*** A DESIGNATION ALONE IS NOT UNIQUE WITHIN A SYSTEM, WHICH IS WHY body_no IS IN THE KEY. *** 162 (system_id, system_body) pairs in the Spansh dump name two bodies each. 160 of those are genuinely different objects, differing in arrival distance, sub-type, ring count or the star/planet distinction itself; the remaining 2 are one body captured twice in the same file, differing only in update_time. Six of the 160 are a star and an Earth-like world sharing the bare system name -- in Leesti, body_no 0 is a K star at 0 Ls and body_no 11 is an ELW at 262 Ls, both designated ''Leesti''. Keying on the designation alone stores one of each pair and discards the other.

A catalogue row carries no index. It takes the lowest real body_no any staged feed gives the same designation, else the lowest main.system_body already holds for it, else -1.

NO KEY IS DECLARED. A full load puts ~570M rows here and an ART index that size does not fit this machine (see schema/system_body.sql). The GROUP BY in the fill makes (system_id, system_body, body_no) unique by construction.';

COMMENT ON COLUMN transform.system_body.system_id IS
'The game''s id64 for the owning system, straight from the feed. Only systems main.system_known holds are admitted, because the designation is stripped against the name it composes.';

COMMENT ON COLUMN transform.system_body.body_no IS
'The body''s index within its system, from the feed''s bodyId (Spansh, EDSM and EDAstro planets carry it). -1 means the index is unknown: a catalogue hit or POI report whose designation no indexed feed or stored row supplies.

*** NOT body_id. *** body_no says WHICH body (0..225); body_id says WHAT KIND it is (1..68, a foreign key). The dumps name this one bodyId, so the collision is in the source rather than in our schema, and reading staging demands care over it.

It is also the entire content of the game''s body address: that value is system_id + (body_no << 55) on every row of the Spansh dump, verified across all 569,697,301 with no exceptions.';

COMMENT ON COLUMN transform.system_body.system_body IS
'The body''s designation within its system: the body name with the system''s full name stripped. The primary star is usually the EMPTY STRING, its body name being the system name exactly. That is a real value and must not become NULL.';

COMMENT ON COLUMN transform.system_body.body_name IS
'One full body name that produced this row, from the highest-priority feed. Used to look the body up in the Spansh dump when ranking ambiguous primaries; not merged.';

COMMENT ON COLUMN transform.system_body.body_id IS
'FK -> body.body_id, the body TYPE, resolved by matching the feed''s sub_type against body.body. NULL where the feed gives no sub_type or an unknown spelling, which means "type unknown" and never "no body". *** Not the body''s index within its system, which is body_no. ***';

COMMENT ON COLUMN transform.system_body.is_primary IS
'TRUE when any feed reporting this body marks it the arrival star. Two TRUE rows for one system are settled after the merge by transform.system_body_primary and the global sweep.';

COMMENT ON COLUMN transform.system_body.discovered_time IS
'Earliest discovery date the rare-star catalogue gives this designation, whatever feed won the row. Written on INSERT only; NULL for every body outside that catalogue.';

COMMENT ON COLUMN transform.system_body.solar_masses IS
'Largest reported solar mass for this body. Stars only; NULL for every planet, which uses earth_masses. One solar mass is about 333,000 Earth masses, so the two never mix.';

COMMENT ON COLUMN transform.system_body.earth_masses IS
'Largest reported Earth mass for this body. Planets only; NULL for every star. Worth roughly 57% of an Earth-like world''s scan value, so a NULL here understates a planet materially.';

COMMENT ON COLUMN transform.system_body.is_terraformable IS
'TRUE when any feed records this body as Terraformable. NULL means unknown, not false: test IS TRUE or IS NOT TRUE rather than relying on falsiness.';

COMMENT ON COLUMN transform.system_body.source IS
'The highest-priority feed reporting this body: spansh, edsm, edastro, edastro_neutron or edastro_rare. The last two are CATALOGUE-ONLY and do not make a system count as scanned.';

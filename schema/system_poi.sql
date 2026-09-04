-- system_poi: which systems hold a point of interest, system-level and body-level in
-- one place.
-- Database: elite_mapping_v2.duckdb (the model).
-- Load order tier 3 -- derived from system_known, system_body, poi and sector.
CREATE TABLE IF NOT EXISTS system_poi (
    system_id BIGINT  NOT NULL,
    poi_id    INTEGER NOT NULL REFERENCES poi (poi_id),
    system    VARCHAR,
    sector    VARCHAR,
    x         DOUBLE,
    y         DOUBLE,
    z         DOUBLE,
    PRIMARY KEY (system_id, poi_id)
);

-- --------------------------------------------------------------------------
-- COMMENTS. Kept in this file, beside the DDL they describe, so a schema change
-- and its documentation cannot drift apart.
-- --------------------------------------------------------------------------

COMMENT ON TABLE system_poi IS
'One row per (system, point of interest): 66,548 of them, unioning the two ways the model attributes a POI. *** THE TWO ATTRIBUTIONS ARE THE POINT. *** A POI pinned to a named body is recorded against the BODY (system_body.id_poi, 10,023 rows), everything else against the SYSTEM (system_known.id_poi, 59,764), so either alone misses real POIs -- and writing the union at query time cost a scan of system_body''s 577,639,044 rows to reach 10,023. That was most of the overlay''s Current sector table (the prediction filter beside it is 23 ms); here the probe is 1.6 ms. *** IT ADDS NO FACTS AND IS NOT A CENSUS. *** Every value is copied; poi is the 260-row dimension and this is the bridge. Absent here means no source attributes a POI, NOT that nobody has looked. DERIVED table: etl/build_system_poi.py.';

COMMENT ON COLUMN system_poi.system_id IS
'THE SAME SURROGATE KEY AS system_known.system_id, copied and never reallocated, so this joins straight back to system_known and system_neutron. Not the game''s id64. No FOREIGN KEY, for the same reason system_neutron''s copy carries none: it is a copy of a key, and the row it came from enforces it.';

COMMENT ON COLUMN system_poi.poi_id IS
'FOREIGN KEY into poi, the 260-row dimension holding the name, class and family. A key and not text, so the wording cannot drift -- read poi.poi and poi.poi_class through the join. Part of the primary key: one system can hold several POIs, each its own row.';

COMMENT ON COLUMN system_poi.system IS
'The FULL, PASTEABLE system name, composed once here. *** THE sector_id = 0 SENTINEL IS ALREADY HANDLED *** -- blind concatenation yields "crafted Charick Drift", which the galaxy map rejects, and 581 POI systems were hit by that bug before it was found.';

COMMENT ON COLUMN system_poi.sector IS
'The sector NAME, copied from sector.sector, so a "what is in this sector" probe needs no join. ''crafted'' for hand-named systems -- that sentinel collects every hand-named system in the galaxy, so filtering on it selects a galaxy-wide population, not a place. Never concatenate this into a system name: system_poi.system already did it correctly.';

COMMENT ON COLUMN system_poi.x IS
'Light years, galactic coordinates of the SYSTEM, copied from system_known -- never the body''s, which the model does not hold. Exact, not a boxel centroid. NULL where system_known has no position, in which case the row cannot be ranked by distance.';

COMMENT ON COLUMN system_poi.y IS
'Light years, galactic coordinates of the system, copied from system_known. See system_poi.x.';

COMMENT ON COLUMN system_poi.z IS
'Light years, galactic coordinates of the system, copied from system_known. See system_poi.x.';

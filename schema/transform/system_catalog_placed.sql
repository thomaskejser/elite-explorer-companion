CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.system_catalog_placed;

CREATE TABLE transform.system_catalog_placed (
    name VARCHAR NOT NULL PRIMARY KEY
);

INSERT INTO transform.system_catalog_placed (name)
SELECT DISTINCT system FROM staging.catalog_parallax WHERE usable;

COMMENT ON TABLE transform.system_catalog_placed IS
'TRANSFORM: every catalogue name that can be placed in 3D -- seeded with the names staging.catalog_parallax holds a usable parallax for, then grown hop by hop across system_catalog_alias by etl/system_catalog/place.sql until a hop adds nothing (at most 8). Rebuilt on every load that finds staging.catalog_parallax; derived, never edited, safe to drop.

A Tycho-2 name has no parallax of its own, but if it is the same star as a Hipparcos name that does, the star has a distance and lands here. Input to transform.system_catalog_coordinate.';

COMMENT ON COLUMN transform.system_catalog_placed.name IS
'A catalogue or game name with a usable distance, directly or through a chain of alias edges.';

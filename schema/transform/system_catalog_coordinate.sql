CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.system_catalog_coordinate;

CREATE TABLE transform.system_catalog_coordinate (
    system             VARCHAR NOT NULL PRIMARY KEY,
    missing_coordinate BOOLEAN NOT NULL
);

INSERT INTO transform.system_catalog_coordinate (system, missing_coordinate)
SELECT c.system,
       NOT EXISTS (SELECT 1 FROM transform.system_catalog_placed p WHERE p.name = c.system)
FROM main.system_catalog c;

COMMENT ON TABLE transform.system_catalog_coordinate IS
'TRANSFORM: main.system_catalog.missing_coordinate as this load computes it, one row per catalogue name, from transform.system_catalog_placed. Rebuilt on every load that finds staging.catalog_parallax; derived, never edited, safe to drop.

When staging.catalog_parallax is absent this table is not built and main.system_catalog.missing_coordinate is left exactly as it was, rather than asserting FALSE it cannot support.';

COMMENT ON COLUMN transform.system_catalog_coordinate.system IS
'The catalogue name, one row per main.system_catalog row.';

COMMENT ON COLUMN transform.system_catalog_coordinate.missing_coordinate IS
'TRUE when the name is absent from transform.system_catalog_placed: no usable parallax for this star in any source held, directly or across the alias graph.';

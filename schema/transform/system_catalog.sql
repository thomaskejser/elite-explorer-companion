CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.system_catalog;

CREATE TABLE transform.system_catalog (
    system      VARCHAR NOT NULL PRIMARY KEY CHECK (trim(system) <> ''),
    type        VARCHAR NOT NULL CHECK (trim(type) <> ''),
    designation VARCHAR NOT NULL CHECK (trim(designation) <> '')
);

INSERT INTO transform.system_catalog (system, type, designation)
SELECT system, type, designation
FROM staging.system_catalog_curated;

COMMENT ON TABLE transform.system_catalog IS
'TRANSFORM: staging.system_catalog_curated shaped exactly as main.system_catalog merges it -- the three columns the file owns. Rebuilt on every load -- derived, never edited, safe to drop.

Its constraints ARE the validation of the hand-editable file: a blank name, type or designation, or one name listed twice, fails HERE before anything reaches main.

system_id and missing_coordinate are NOT here. Both are derived by the loader after the merge, from system_known and system_catalog_alias, and never come from the file.';

COMMENT ON COLUMN transform.system_catalog.system IS
'The natural key the merge matches on. Not trimmed or respelled: it must paste into the galaxy map exactly.';

COMMENT ON COLUMN transform.system_catalog.type IS
'Source catalogue, required. Updated in main when the file changes it.';

COMMENT ON COLUMN transform.system_catalog.designation IS
'Identifier within the catalogue, required. Updated in main when the file changes it.';

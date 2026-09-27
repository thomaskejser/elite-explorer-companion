CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.system_catalog_alias;

CREATE TABLE transform.system_catalog_alias (
    system_a VARCHAR NOT NULL CHECK (trim(system_a) <> ''),
    system_b VARCHAR NOT NULL CHECK (trim(system_b) <> ''),
    source   VARCHAR NOT NULL CHECK (trim(source) <> ''),
    PRIMARY KEY (system_a, system_b),
    CHECK (system_a < system_b)
);

INSERT INTO transform.system_catalog_alias (system_a, system_b, source)
SELECT system_a, system_b, source
FROM staging.system_catalog_alias_curated;

COMMENT ON TABLE transform.system_catalog_alias IS
'TRANSFORM: staging.system_catalog_alias_curated shaped exactly as main.system_catalog_alias merges it. Rebuilt on every load -- derived, never edited, safe to drop.

Its constraints ARE the validation of the hand-editable file: a blank endpoint, a pair stored out of canonical order (system_a >= system_b) or the same pair twice fails HERE, before anything reaches main. An unordered pair would otherwise be stored as a second edge for the same identity.

It is also the retraction list: an edge in main that this table does not hold is DELETED by etl/system_catalog_alias/delete.sql, because a withdrawn cross-identification is wrong rather than retired.';

COMMENT ON COLUMN transform.system_catalog_alias.system_a IS
'The lesser endpoint, CHECKed to sort before system_b. Not trimmed or respelled: the string must match system_catalog.system or a game name byte for byte.';

COMMENT ON COLUMN transform.system_catalog_alias.system_b IS
'The greater endpoint.';

COMMENT ON COLUMN transform.system_catalog_alias.source IS
'Provenance of the assertion, required. The only column the merge ever updates.';

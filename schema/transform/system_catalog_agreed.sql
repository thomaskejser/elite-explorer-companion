CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.system_catalog_agreed;

CREATE TABLE transform.system_catalog_agreed (
    system    VARCHAR NOT NULL PRIMARY KEY,
    system_id BIGINT  NOT NULL
);

INSERT INTO transform.system_catalog_agreed (system, system_id)
WITH neighbours AS (
    SELECT system_a AS name, system_b AS other FROM main.system_catalog_alias
    UNION ALL
    SELECT system_b AS name, system_a AS other FROM main.system_catalog_alias
),
resolved AS (
    SELECT system AS name, system_id FROM main.system_catalog
    WHERE system_id IS NOT NULL
    UNION ALL
    SELECT system_in_sector AS name, system_id FROM main.system_known
    WHERE sector_id = 0
)
SELECT n.name, min(r.system_id)
FROM neighbours n
JOIN resolved r ON r.name = n.other
JOIN main.system_catalog u ON u.system = n.name AND u.system_id IS NULL
GROUP BY n.name
HAVING count(DISTINCT r.system_id) = 1;

COMMENT ON TABLE transform.system_catalog_agreed IS
'TRANSFORM: ONE PASS of phase 2 of system_catalog.system_id resolution -- every still-unresolved catalogue name whose alias neighbours all agree on one game system. Rebuilt before every pass by etl/system_catalog/load.py, which merges it and repeats until a pass finds nothing (at most 12); derived, never edited, safe to drop.

A neighbour counts as resolved when it is a system_catalog row that already carries a system_id, or a hand-named game system of that name -- the second is how edges ending at a GAME name (Sirius, Alpha Centauri) reach the bright stars.

*** A NAME WHOSE NEIGHBOURS DISAGREE IS NOT HERE. *** HAVING count(DISTINCT system_id) = 1 refuses to propagate when two neighbours mean two different systems, and a game name held by several systems contributes all of them, so it disagrees with itself and blocks rather than being guessed at. The loader reports how many names that leaves NULL.';

COMMENT ON COLUMN transform.system_catalog_agreed.system IS
'A main.system_catalog name that has system_id NULL at the start of this pass. Every row here is therefore an update the pass will make.';

COMMENT ON COLUMN transform.system_catalog_agreed.system_id IS
'The single game system all of this name''s resolved neighbours point at.';

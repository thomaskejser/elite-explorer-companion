CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.system_catalog_name;

CREATE TABLE transform.system_catalog_name (
    system     VARCHAR NOT NULL PRIMARY KEY,
    system_id  BIGINT,
    candidates INTEGER NOT NULL,
    CHECK ((candidates = 1) = (system_id IS NOT NULL))
);

INSERT INTO transform.system_catalog_name (system, system_id, candidates)
SELECT c.system,
       CASE WHEN count(k.system_id) = 1 THEN min(k.system_id) END,
       CAST(count(k.system_id) AS INTEGER)
FROM main.system_catalog c
LEFT JOIN main.system_known k
       ON k.sector_id = 0 AND k.system_in_sector = c.system
GROUP BY c.system;

COMMENT ON TABLE transform.system_catalog_name IS
'TRANSFORM: phase 1 of system_catalog.system_id resolution -- every main.system_catalog row matched BY NAME against the hand-named game systems (system_known rows at sector_id = 0, where the full name IS system_in_sector). One row per catalogue name. Rebuilt on every load, after the row merge, because it reads main; derived, never edited, safe to drop.

*** A NAME HELD BY MORE THAN ONE GAME SYSTEM RESOLVES TO NULL. *** 1,477 hand-named system names belong to more than one system_known row (Frontier shipped the same designation several times). Picking one would write a coin-flip id into the model, so such a name gets system_id NULL here and candidates > 1, and the alias walk may still resolve it through a neighbour that agrees.

The loader MERGEs this into main.system_catalog.system_id for every row, which is also the reset step: every alias-resolved value goes back to NULL (or to its name match) and is re-derived from today''s edges.';

COMMENT ON COLUMN transform.system_catalog_name.system IS
'The catalogue name, one row per main.system_catalog row.';

COMMENT ON COLUMN transform.system_catalog_name.system_id IS
'The one hand-named game system of exactly this name, or NULL when there is none or more than one. Never a pick among several.';

COMMENT ON COLUMN transform.system_catalog_name.candidates IS
'How many hand-named game systems carry exactly this name: 0 not shipped under this spelling, 1 resolved, more than 1 AMBIGUOUS and deliberately left NULL. Reported by the loader, not stored in main.';

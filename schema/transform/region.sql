CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.region;

CREATE TABLE transform.region (
    region_id BIGINT  NOT NULL PRIMARY KEY,
    region    VARCHAR NOT NULL UNIQUE CHECK (trim(region) <> '')
);

INSERT INTO transform.region (region_id, region)
WITH counted AS (
    SELECT CAST(regexp_extract(region_name, '([0-9]+)', 1) AS BIGINT) AS region_id,
           region_name_localised                                     AS region,
           count(*)                                                  AS n
    FROM staging.canonn_codex_event
    WHERE region_name IS NOT NULL AND region_name_localised IS NOT NULL
    GROUP BY 1, 2
),
ranked AS (
    SELECT *, row_number() OVER (PARTITION BY region_id ORDER BY n DESC, region) AS rk
    FROM counted
)
SELECT region_id, region FROM ranked WHERE rk = 1;

COMMENT ON TABLE transform.region IS
'TRANSFORM: staging.canonn_codex_event reduced to one English name per region_id, shaped exactly as main.region merges it. Rebuilt from staging on every load -- derived, never edited, and safe to drop.

Its constraints are the input validation: NOT NULL, both columns UNIQUE, no blank name. Bad input fails HERE, before anything reaches main.

The modal pick is a HEURISTIC, not a guarantee: it returns English because English reporters are the plurality, not because the feed says which language a row is in. A wrong name is corrected by changing schema/transform/region.sql, since nothing downstream of it can tell.';

COMMENT ON COLUMN transform.region.region_id IS
'The GAME''s region id, parsed out of the region_name token. Never allocated here -- main.region takes it as given.';

COMMENT ON COLUMN transform.region.region IS
'Modal region_name_localised for this id. UNIQUE and non-blank, enforced above: two regions sharing a name means the modal pick has gone wrong, and it must fail rather than merge.';

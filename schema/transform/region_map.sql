CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.region_map;

CREATE TABLE transform.region_map (
    z_row     INTEGER NOT NULL CHECK (z_row BETWEEN 0 AND 2047),
    x_start   INTEGER NOT NULL CHECK (x_start BETWEEN 0 AND 2047),
    length    INTEGER NOT NULL CHECK (length BETWEEN 1 AND 2048),
    region_id BIGINT  NOT NULL,
    PRIMARY KEY (z_row, x_start)
);

INSERT INTO transform.region_map (z_row, x_start, length, region_id)
WITH placed AS (
    SELECT z_row, length, region,
           sum(length) OVER (PARTITION BY z_row ORDER BY run_no) - length AS x_start
    FROM staging.klightspeed_region_map
)
SELECT p.z_row, p.x_start, p.length, r.region_id
FROM placed p
JOIN main.region r ON r.region = p.region OR r.region = 'The ' || p.region
WHERE p.region IS NOT NULL;

COMMENT ON TABLE transform.region_map IS
'TRANSFORM: staging.klightspeed_region_map placed on the grid and resolved to region_id, shaped exactly as main.region_map merges it. Runs outside every region are dropped. Rebuilt from staging on every load -- derived, never edited, and safe to drop. A run whose name matches no region is dropped too; etl/region_map/load.py counts those and says so.';

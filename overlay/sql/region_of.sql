WITH by_sector AS (
    SELECT region_id FROM {{MODEL}}.sector WHERE sector = ?
),
by_position AS (
    SELECT region_id FROM {{MODEL}}.region_map
    WHERE z_row = floor((?::DOUBLE + 24105) * 83 / 4096)
      AND floor((?::DOUBLE + 49985) * 83 / 4096) BETWEEN x_start AND x_start + length - 1
)
SELECT r.region_id, r.region FROM {{MODEL}}.region r
WHERE r.region_id = coalesce((SELECT region_id FROM by_sector), (SELECT region_id FROM by_position))

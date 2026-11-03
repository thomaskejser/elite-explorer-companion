WITH runs AS (
    SELECT floor(z_row * (4096.0 / 83) / 1280)::BIGINT AS z_lo,
           floor(((z_row + 1) * (4096.0 / 83) - 0.001) / 1280)::BIGINT AS z_hi,
           floor(x_start * (4096.0 / 83) / 1280)::BIGINT AS x_lo,
           floor(((x_start + length) * (4096.0 / 83) - 0.001) / 1280)::BIGINT AS x_hi
    FROM {{MODEL}}.region_map
    WHERE region_id = ?
),
by_row AS (
    SELECT DISTINCT unnest(range(x_lo, x_hi + 1)) AS cx, z_lo, z_hi
    FROM runs
),
columns AS (
    SELECT DISTINCT cx, unnest(range(z_lo, z_hi + 1)) AS cz
    FROM by_row
),
sectors AS (
    SELECT s.sector_id, s.sector
    FROM {{MODEL}}.sector s
    JOIN columns c ON s.sector_id % 128 = c.cx AND s.sector_id // 16384 = c.cz
    WHERE s.sector_id > 0
),
conf AS (
    SELECT c.sector, {{CONF_COUNTS}}
    FROM system_confirmed c
    WHERE {{CONF_OPEN}}
    GROUP BY c.sector
),
predicted AS (
    SELECT p.sector, count(*) AS n, {{P_SUMS}}
    FROM {{MODEL}}.system_predicted p
    {{SEEN_JOIN}}
    WHERE p.sector IN (SELECT sector FROM sectors) AND (? OR NOT p.is_catalog) AND {{OFFERABLE}}
    GROUP BY p.sector
)
SELECT s.sector, coalesce(p.n, 0) AS n, coalesce(k.systems, 0) AS known, {{P_COLUMNS_P}}, s.sector_id, {{CONF_COLUMNS}}
FROM sectors s
LEFT JOIN predicted p ON p.sector = s.sector
LEFT JOIN conf f ON f.sector = s.sector
LEFT JOIN {{MODEL}}.sector_known k ON k.sector_id = s.sector_id
ORDER BY s.sector_id
;
WITH predicted AS (
    SELECT p.sector, {{P_SUMS}}
    FROM {{MODEL}}.system_predicted p
    {{SEEN_JOIN}}
    WHERE (? OR NOT p.is_catalog) AND {{OFFERABLE}}
    GROUP BY p.sector
),
by_column AS (
    SELECT s.sector_id % 128 AS cx, s.sector_id // 16384 AS cz, {{P_SUMS_BARE}}
    FROM predicted
    JOIN {{MODEL}}.sector s ON s.sector = predicted.sector
    WHERE s.sector_id > 0
    GROUP BY 1, 2
)
SELECT 'galaxy' AS sector, 0 AS n, 0 AS known, {{P_MAX_BARE}}, NULL::BIGINT AS sector_id
FROM by_column

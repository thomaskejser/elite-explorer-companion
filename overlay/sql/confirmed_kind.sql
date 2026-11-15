WITH {{CONFIRMED_CTE}},
scored AS (
  SELECT *,
         CASE WHEN x IS NULL THEN NULL
              ELSE sqrt(pow(x - ?, 2) + pow(y - ?, 2) + pow(z - ?, 2)) END AS dist_ly
  FROM confirmed
  WHERE kind = ?
    AND (CAST(? AS VARCHAR) IS NULL OR sector = ?)
    AND (CAST(? AS BIGINT) IS NULL OR sector IN (SELECT sector FROM {{MODEL}}.sector WHERE region_id = ?))
)
SELECT system,
       star_class AS detail,
       dist_ly, FALSE AS dist_approx,
       count(*) OVER () AS kind_count,
       {{ROW_CONFIRMED}} AS row_grp,
       x, y, z, star_class
FROM scored
ORDER BY dist_ly IS NULL, dist_ly, system
LIMIT ?

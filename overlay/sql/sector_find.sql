WITH found AS (
  SELECT s.sector_id, k.systems,
         CASE WHEN s.sector_id > 0 THEN (s.sector_id % 128) * 1280 - 49985 ELSE s.x - s.radius END AS x0_ly,
         CASE WHEN s.sector_id > 0 THEN (s.sector_id // 16384) * 1280 - 24105 ELSE s.z - s.radius END AS z0_ly,
         CASE WHEN s.sector_id > 0 THEN 1280 ELSE 2 * s.radius END AS side_ly
  FROM {{MODEL}}.sector s
  LEFT JOIN {{MODEL}}.sector_known k USING (sector_id)
  WHERE s.sector = ? AND s.sector_id <> 0
)
SELECT sector_id, systems,
       (x0_ly + 49985) * 83 / 4096 AS x0,
       (z0_ly + 24105) * 83 / 4096 AS z0,
       (x0_ly + side_ly + 49985) * 83 / 4096 AS x1,
       (z0_ly + side_ly + 24105) * 83 / 4096 AS z1
FROM found

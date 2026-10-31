WITH ship AS (
  SELECT ?::DOUBLE AS px, ?::DOUBLE AS py, ?::DOUBLE AS pz
),
block AS (
  SELECT (floor((px + 49985) / 1280) - 1) * 1280 AS bx,
         (floor((pz + 24105) / 1280) - 1) * 1280 AS bz,
         {{MINIMAP_PAD_CELLS}} * 8192.0 / 83 AS pad
  FROM ship
  WHERE px IS NOT NULL AND pz IS NOT NULL
),
win AS (
  SELECT floor((bx - pad) / (4096.0 / 83))::BIGINT AS x0,
         floor((bx + 3840 + pad) / (4096.0 / 83))::BIGINT AS x1,
         floor((bz - pad) / (4096.0 / 83))::BIGINT AS z0,
         floor((bz + 3840 + pad) / (4096.0 / 83))::BIGINT AS z1
  FROM block
)
SELECT r.z_row, r.x_start, r.length, r.region_id, w.x0, w.z0, w.x1 - w.x0 + 1 AS cols, w.z1 - w.z0 + 1 AS rows
FROM win w
JOIN {{MODEL}}.region_map r
  ON r.z_row BETWEEN w.z0 AND w.z1
 AND r.x_start <= w.x1
 AND r.x_start + r.length > w.x0

WITH ship AS (
  SELECT ?::DOUBLE AS px, ?::DOUBLE AS py, ?::DOUBLE AS pz
),
block AS (
  SELECT (floor((px + 49985) / 1280) - 1) * 1280 AS bx,
         (floor((pz + 24105) / 1280) - 1) * 1280 AS bz
  FROM ship
  WHERE px IS NOT NULL AND pz IS NOT NULL
),
lo AS (
  SELECT bx, bz,
         floor(bx / (8192.0 / 83))::BIGINT - {{MINIMAP_PAD_CELLS}} AS x_lo,
         floor(bz / (8192.0 / 83))::BIGINT - {{MINIMAP_PAD_CELLS}} AS z_lo
  FROM block
)
SELECT d.cell_x - l.x_lo AS ix,
       d.cell_z - l.z_lo AS iz,
       d.systems,
       l.x_lo * (8192.0 / 83) - l.bx AS x_off,
       l.z_lo * (8192.0 / 83) - l.bz AS z_off,
       8192.0 / 83 AS cell_ly,
       l.bx - 49985 AS block_x,
       l.bz - 24105 AS block_z
FROM lo l
LEFT JOIN {{MODEL}}.galaxy_density d
  ON d.cell_x BETWEEN l.x_lo AND l.x_lo + {{MINIMAP_CELLS}} - 1
 AND d.cell_z BETWEEN l.z_lo AND l.z_lo + {{MINIMAP_CELLS}} - 1

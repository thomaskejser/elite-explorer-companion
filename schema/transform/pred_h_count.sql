CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.pred_h_count;

CREATE TABLE transform.pred_h_count (
    sector     VARCHAR NOT NULL PRIMARY KEY,
    n          BIGINT  NOT NULL,
    n_scanned  BIGINT  NOT NULL,
    found_wr   BIGINT  NOT NULL,
    found_bh   BIGINT  NOT NULL,
    n_catalog  BIGINT  NOT NULL,
    wr_layer   BOOLEAN NOT NULL,
    size_band  INTEGER NOT NULL,
    cross_d    DOUBLE  NOT NULL
);

INSERT INTO transform.pred_h_count
WITH h AS (
  SELECT s.sector, k.system_id, k.boxel_index, k.x, k.y, k.z
  FROM main.system_known k
  JOIN main.sector s ON s.sector_id = k.sector_id
  WHERE k.mass_code = 'h' AND k.cube_id = 'AA-A' AND k.sub_cube_id = 0 AND NOT s.is_crafted
),
counted AS (
  SELECT h.sector,
         max(h.boxel_index) + 1 AS n,
         count(*) FILTER (WHERE l.n_scan_rows > 0 AND l.n_stars > 0) AS n_scanned,
         coalesce(sum(l.has_wr), 0) AS found_wr,
         coalesce(sum(l.has_bh), 0) AS found_bh,
         mode(floor((h.y + 40985) / 1280)) = 32 AS wr_layer,
         least(abs(avg(h.x)), abs(avg(h.z))) AS cross_d
  FROM h
  LEFT JOIN transform.pred_labels l ON l.system_id = h.system_id
  GROUP BY 1
),
pooled AS (
  SELECT sector, count(*) AS n_catalog
  FROM transform.pred_pool
  WHERE mass_code = 'h' AND is_catalog
  GROUP BY 1
)
SELECT c.sector, c.n, c.n_scanned, c.found_wr, c.found_bh, coalesce(p.n_catalog, 0),
       c.wr_layer,
       CASE WHEN c.n < 200 THEN 0 WHEN c.n < 400 THEN 1 ELSE 2 END,
       round(c.cross_d, 3)
FROM counted c
LEFT JOIN pooled p USING (sector);

COMMENT ON TABLE transform.pred_h_count IS
'TRANSFORM: one row per procedural sector holding a known mass-h system: how many mass-h systems it holds and how many Wolf-Rayets and black holes are already found in them. The input to transform.pred_h_type and transform.pred_h_sector; rebuilt on every main.system_predicted load, safe to drop.

A procedural sector has a single mass-h boxel, AA-A, numbered from 0 without gaps, so its count is its highest known number plus one: a random galaxy-map probe of 48 sectors at every radius found the number above the highest known one in 8 and the number five above it in none (MODEL.md).';

COMMENT ON COLUMN transform.pred_h_count.sector IS 'Sector name, as transform.pred_pool.sector holds it.';
COMMENT ON COLUMN transform.pred_h_count.n IS 'Mass-h systems in the sector: the highest known AA-A h number plus one.';
COMMENT ON COLUMN transform.pred_h_count.n_scanned IS 'Mass-h systems with a scanned star row (transform.pred_labels, n_scan_rows > 0 and n_stars > 0).';
COMMENT ON COLUMN transform.pred_h_count.found_wr IS 'Mass-h systems with a Wolf-Rayet row from any source, catalogue hits included, since a catalogued Wolf-Rayet is no longer there to find.';
COMMENT ON COLUMN transform.pred_h_count.found_bh IS 'Mass-h systems with a black-hole row from any source. See found_wr.';
COMMENT ON COLUMN transform.pred_h_count.n_catalog IS 'Catalogued mass-h systems with no body rows (transform.pred_pool, is_catalog).';
COMMENT ON COLUMN transform.pred_h_count.wr_layer IS 'TRUE when the sector lies in the grid layer from y = -25 to +1,255 ly, where nearly every sector is Wolf-Rayet-rich.';
COMMENT ON COLUMN transform.pred_h_count.size_band IS '0 for fewer than 200 mass-h systems, 1 for 200-399, 2 for 400 or more.';
COMMENT ON COLUMN transform.pred_h_count.cross_d IS 'Distance of the sector''s mean mass-h position from the nearer of the x = 0 and z = 0 planes, ly, 3 dp.';

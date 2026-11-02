CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.pred_boxel_gap;

CREATE TABLE transform.pred_boxel_gap (
    sector_id   BIGINT  NOT NULL,
    cube_id     VARCHAR NOT NULL,
    mass_code   VARCHAR NOT NULL,
    sub_cube_id INTEGER,
    sector      VARCHAR,
    boxel_index BIGINT  NOT NULL,
    x           DOUBLE,
    y           DOUBLE,
    z           DOUBLE
);

INSERT INTO transform.pred_boxel_gap
WITH bx AS (
  SELECT k.sector_id, k.cube_id, k.mass_code, k.sub_cube_id,
         min(k.boxel_index) AS mn, max(k.boxel_index) AS mx, count(*) AS obs,
         round(avg(k.x), 5) AS x, round(avg(k.y), 5) AS y, round(avg(k.z), 5) AS z,
         any_value(sc.sector) AS sector
  FROM main.system_known k
  LEFT JOIN main.sector sc ON sc.sector_id = k.sector_id
  WHERE k.mass_code IN ('e', 'f', 'g', 'h')
    AND k.boxel_index IS NOT NULL AND k.cube_id IS NOT NULL
  GROUP BY 1, 2, 3, 4
  HAVING max(k.boxel_index) > min(k.boxel_index)
     AND count(*)::DOUBLE / (max(k.boxel_index) - min(k.boxel_index) + 1) >= 0.5
)
SELECT b.sector_id, b.cube_id, b.mass_code, b.sub_cube_id, b.sector,
       t.gidx, b.x, b.y, b.z
FROM bx b, unnest(range(b.mn, b.mx + 1)) AS t(gidx)
WHERE NOT EXISTS (SELECT 1 FROM main.system_known k
                  WHERE k.sector_id = b.sector_id AND k.cube_id = b.cube_id
                    AND k.mass_code = b.mass_code AND k.sub_cube_id = b.sub_cube_id
                    AND k.boxel_index = t.gidx);

COMMENT ON TABLE transform.pred_boxel_gap IS
'TRANSFORM: boxel indices missing from main.system_known inside e/f/g/h boxels whose known indices are dense (at least half of min..max present). Each row is a system the generator almost certainly placed that no dump reports -- the boxel-predicted half of main.system_predicted. Rebuilt on every load, safe to drop.

*** A PREDICTED NAME, NOT A KNOWN SYSTEM. *** Nothing here has an id64 or real coordinates; x/y/z are the boxel''s mean position. An index above the highest known one is never generated, so a boxel''s tail is invisible here.';

COMMENT ON COLUMN transform.pred_boxel_gap.sector_id IS 'main.system_known.sector_id of the boxel.';
COMMENT ON COLUMN transform.pred_boxel_gap.cube_id IS 'The AB-C letter triple of the boxel.';
COMMENT ON COLUMN transform.pred_boxel_gap.mass_code IS 'Boxel mass code, e to h.';
COMMENT ON COLUMN transform.pred_boxel_gap.sub_cube_id IS 'The number before the hyphen, 0 when the name has none.';
COMMENT ON COLUMN transform.pred_boxel_gap.sector IS 'The sector NAME from main.sector, used to compose the predicted system name. ''crafted'' would be the sentinel, which never reaches here because hand-named systems carry no boxel.';
COMMENT ON COLUMN transform.pred_boxel_gap.boxel_index IS 'The missing index, strictly between the boxel''s lowest and highest known index.';
COMMENT ON COLUMN transform.pred_boxel_gap.x IS 'Mean x of the boxel''s KNOWN systems, 5 dp. An approximation of where the missing system is, never its position.';
COMMENT ON COLUMN transform.pred_boxel_gap.y IS 'Mean y of the boxel''s known systems. See x.';
COMMENT ON COLUMN transform.pred_boxel_gap.z IS 'Mean z of the boxel''s known systems. See x.';

CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.pred_pool;

CREATE TABLE transform.pred_pool (
    system_name VARCHAR NOT NULL,
    system_id64 BIGINT,
    is_catalog  BOOLEAN NOT NULL,
    mass_code   VARCHAR NOT NULL,
    plane_r     DOUBLE,
    x           DOUBLE,
    y           DOUBLE,
    z           DOUBLE,
    r_sgra      DOUBLE,
    boxel       VARCHAR,
    sector      VARCHAR
);

INSERT INTO transform.pred_pool
WITH known AS (
  SELECT k.system_id, k.system_id AS id64, k.mass_code, k.x, k.y, k.z,
         sc.sector AS sector_name,
         CASE WHEN sc.sector IS NULL OR k.sector_id = 0 THEN k.system_in_sector
              ELSE sc.sector || ' ' || k.system_in_sector END AS system_name
  FROM main.system_known k
  LEFT JOIN main.sector sc ON sc.sector_id = k.sector_id
  WHERE k.mass_code IN ('e', 'f', 'g', 'h')
),
unscanned AS (
  SELECT * FROM known u
  WHERE NOT EXISTS (SELECT 1 FROM main.system_body sb WHERE sb.system_id = u.system_id)
),
gap AS (
  SELECT CASE WHEN g.sector IS NULL THEN '' ELSE g.sector || ' ' END
         || g.cube_id || ' ' || g.mass_code
         || CASE WHEN g.sub_cube_id = 0 THEN ''
                 ELSE CAST(g.sub_cube_id AS VARCHAR) || '-' END
         || CAST(g.boxel_index AS VARCHAR) AS system_name,
         g.mass_code, g.x, g.y, g.z, g.sector AS sector_name
  FROM transform.pred_boxel_gap g
)
SELECT u.system_name, u.id64, true, u.mass_code,
       sqrt(pow(u.x - 25.21875, 2) + pow(u.z - 25899.96875, 2)),
       u.x, u.y, u.z,
       sqrt(pow(u.x - 25.21875, 2) + pow(u.y + 20.90625, 2)
          + pow(u.z - 25899.96875, 2)),
       CASE WHEN regexp_extract(u.system_name, '([0-9]+(-[0-9]+)?)$', 1) LIKE '%-%'
            THEN regexp_replace(u.system_name, '[0-9]+(-[0-9]+)?$', '') || '#'
                 || split_part(regexp_extract(u.system_name, '([0-9]+(-[0-9]+)?)$', 1), '-', 1)
            ELSE regexp_replace(u.system_name, '[0-9]+(-[0-9]+)?$', '') END,
       u.sector_name
FROM unscanned u
UNION ALL
SELECT g.system_name, NULL, false, g.mass_code,
       sqrt(pow(g.x - 25.21875, 2) + pow(g.z - 25899.96875, 2)),
       g.x, g.y, g.z,
       sqrt(pow(g.x - 25.21875, 2) + pow(g.y + 20.90625, 2)
          + pow(g.z - 25899.96875, 2)),
       CASE WHEN regexp_extract(g.system_name, '([0-9]+(-[0-9]+)?)$', 1) LIKE '%-%'
            THEN regexp_replace(g.system_name, '[0-9]+(-[0-9]+)?$', '') || '#'
                 || split_part(regexp_extract(g.system_name, '([0-9]+(-[0-9]+)?)$', 1), '-', 1)
            ELSE regexp_replace(g.system_name, '[0-9]+(-[0-9]+)?$', '') END,
       g.sector_name
FROM gap g
WHERE NOT EXISTS (SELECT 1 FROM known kn WHERE kn.system_name = g.system_name);

COMMENT ON TABLE transform.pred_pool IS
'TRANSFORM: the candidate pool main.system_predicted scores -- every e/f/g/h system main.system_known holds with NO main.system_body row (is_catalog TRUE), plus every boxel gap from transform.pred_boxel_gap whose composed name is not already known (is_catalog FALSE). Rebuilt on every load, safe to drop.

No key constraint here on purpose: the loader counts duplicate system_name values and refuses with a readable message before transform.system_predicted, whose PRIMARY KEY would otherwise fail less legibly.

*** "NO BODY ROW" IS "NOBODY REPORTED A SCAN", NOT "UNEXPLORED". ***';

COMMENT ON COLUMN transform.pred_pool.system_name IS 'Full system name, composed from sector + system_in_sector (sector_id 0 stands alone) or, for a gap, from the boxel parts. The natural key main.system_predicted merges on -- see the duplicate check in the loader.';
COMMENT ON COLUMN transform.pred_pool.system_id64 IS 'The game''s id64 for a catalogued system; NULL for a boxel-predicted one, which no feed has reported.';
COMMENT ON COLUMN transform.pred_pool.is_catalog IS 'TRUE: in main.system_known but unscanned. FALSE: predicted from a boxel gap, in no dump at all.';
COMMENT ON COLUMN transform.pred_pool.mass_code IS 'Boxel mass code, e to h.';
COMMENT ON COLUMN transform.pred_pool.plane_r IS 'Distance from Sgr A* in the x/z plane, ly, unrounded. Selects the rate band.';
COMMENT ON COLUMN transform.pred_pool.x IS 'Galactic x, ly. The boxel mean for a predicted row.';
COMMENT ON COLUMN transform.pred_pool.y IS 'Galactic y, ly. See x.';
COMMENT ON COLUMN transform.pred_pool.z IS 'Galactic z, ly. See x.';
COMMENT ON COLUMN transform.pred_pool.r_sgra IS '3-D distance from Sgr A*, ly, unrounded.';
COMMENT ON COLUMN transform.pred_pool.boxel IS 'The name with its trailing index removed, and #<sub_cube> appended when the name has one -- groups systems of one boxel.';
COMMENT ON COLUMN transform.pred_pool.sector IS 'Sector name, NULL when main.sector has no row.';

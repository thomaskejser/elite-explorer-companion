CREATE SCHEMA IF NOT EXISTS transform;

CREATE OR REPLACE TABLE transform.system_green_giant AS
WITH landed AS MATERIALIZED (
  SELECT system_id, body, class, surface_temp_k, kind,
         ggg_landing(kind, surface_temp_k, ggg_depth(surface_temp_k, earth_masses, radius * 1000)) AS landing
  FROM (SELECT b.system_id64 AS system_id, b.name AS body, b.sub_type AS class, b.surface_temp_k,
               b.earth_masses, b.radius, ggg_kind(b.sub_type) AS kind
        FROM staging.spansh_galaxy_body b
        WHERE (b.sub_type ILIKE '%gas giant%' OR b.sub_type = 'Water giant')
          AND b.surface_temp_k IS NOT NULL
          AND b.surface_temp_k <> round(b.surface_temp_k)
          AND b.earth_masses > 0
          AND b.radius > 0)
  WHERE kind IS NOT NULL
),
giants AS (
  SELECT system_id, body, class, surface_temp_k, ggg_verdict_from(kind, surface_temp_k, landing) AS verdict
  FROM landed
  WHERE landing <> 'OFF'
)
SELECT g.system_id, g.body,
       CASE WHEN k.sector_id = 0 THEN k.system_in_sector ELSE sc.sector || ' ' || k.system_in_sector END AS system,
       g.class, g.surface_temp_k, g.verdict, k.x, k.y, k.z
FROM giants g
JOIN main.system_known k ON k.system_id = g.system_id
JOIN main.sector sc ON sc.sector_id = k.sector_id
WHERE g.verdict IN ('GREEN', 'GREEN_LOW_CONFIDENCE')
QUALIFY row_number() OVER (PARTITION BY g.system_id, g.body ORDER BY g.verdict) = 1;

COMMENT ON TABLE transform.system_green_giant IS 'TRANSFORM: the gas giants of staging.spansh_galaxy_body that ggg_verdict calls green, leaving out every whole-number surface_temp_k because Spansh rounds some temperatures to whole kelvins and the cracks sit on whole numbers, named and placed through main.system_known, shaped exactly as main.system_green_giant merges it. Rebuilt on every load, safe to drop.';

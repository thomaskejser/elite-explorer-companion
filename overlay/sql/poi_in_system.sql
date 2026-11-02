WITH found AS (
  SELECT min(sp.poi_id) AS poi_id
  FROM {{MODEL}}.system_poi sp WHERE sp.system = ?
)
SELECT f.poi_id, p.poi, p.poi_class
FROM found f JOIN {{MODEL}}.poi p ON p.poi_id = f.poi_id

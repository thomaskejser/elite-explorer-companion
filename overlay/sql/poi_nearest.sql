WITH near AS (
  SELECT sp.system, min(po.poi) AS poi, min(po.poi_class) AS poi_class,
         max(sp.x) AS x, max(sp.y) AS y, max(sp.z) AS z,
         sqrt(pow(max(sp.x) - ?, 2) + pow(max(sp.y) - ?, 2) + pow(max(sp.z) - ?, 2)) AS dist_ly
  FROM {{MODEL}}.system_poi sp
  JOIN {{MODEL}}.poi po ON po.poi_id = sp.poi_id
  WHERE sp.x IS NOT NULL
    AND sp.system NOT IN (SELECT system FROM poi_visited)
    AND sp.system NOT IN (SELECT system FROM system_visited)
  GROUP BY sp.system
  ORDER BY dist_ly, sp.system
  LIMIT ?
)
SELECT row_number() OVER (ORDER BY dist_ly, system) AS rank,
       system,
       'POI' AS type_label,
       dist_ly, FALSE AS dist_approx,
       {{P_NULLS}},
       {{ROW_POI}} AS row_grp,
       poi AS wide_text,
       poi AS detail, NULL::VARCHAR AS mass_code,
       NULL::VARCHAR AS boxel,
       x, y, z,
       NULL::DOUBLE AS dist_sol, NULL::VARCHAR AS star_class
FROM near ORDER BY dist_ly, system

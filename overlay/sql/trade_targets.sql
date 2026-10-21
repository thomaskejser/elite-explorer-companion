WITH services AS (
  SELECT technology_broker || ' tech broker' AS kind,
         CASE technology_broker WHEN 'Human' THEN 1 ELSE 2 END AS ord,
         system, station, distance_to_arrival_ls, x, y, z
  FROM {{MODEL}}.station_service
  WHERE is_listed AND technology_broker IS NOT NULL AND x IS NOT NULL
  UNION ALL
  SELECT material_trader || ' material trader',
         CASE material_trader WHEN 'Raw' THEN 3 WHEN 'Manufactured' THEN 4 ELSE 5 END,
         system, station, distance_to_arrival_ls, x, y, z
  FROM {{MODEL}}.station_service
  WHERE is_listed AND material_trader IS NOT NULL AND x IS NOT NULL
),
measured AS (
  SELECT *, sqrt(pow(x - ?, 2) + pow(y - ?, 2) + pow(z - ?, 2)) AS dist_ly FROM services
),
ranked AS (
  SELECT *, row_number() OVER (PARTITION BY kind ORDER BY dist_ly, station) AS rn FROM measured
)
SELECT kind, system, station, dist_ly, distance_to_arrival_ls
FROM ranked
WHERE rn = 1
ORDER BY ord

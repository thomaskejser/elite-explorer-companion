WITH amenities AS (
  SELECT CASE WHEN is_carrier THEN 'Universal Cartographics (carrier)' ELSE 'Universal Cartographics' END AS kind,
         CASE WHEN is_carrier THEN 2 ELSE 1 END AS ord,
         system, station, distance_to_arrival_ls, x, y, z
  FROM {{MODEL}}.station
  WHERE is_listed AND has_universal_cartographics
    AND (NOT is_carrier OR last_reported >= now() - INTERVAL {{CARRIER_FRESH_DAYS}} DAY)
  UNION ALL
  SELECT 'Vista Genomics', 3, system, station, distance_to_arrival_ls, x, y, z
  FROM {{MODEL}}.station
  WHERE is_listed AND has_vista_genomics AND NOT is_carrier
  UNION ALL
  SELECT 'Large pad, repair and rearm', 4, system, station, distance_to_arrival_ls, x, y, z
  FROM {{MODEL}}.station
  WHERE is_listed AND has_repair AND has_restock AND large_pads > 0 AND NOT is_carrier
),
services AS (
  SELECT kind, ord, system, station, distance_to_arrival_ls, x, y, z FROM amenities
  UNION ALL
  SELECT technology_broker || ' tech broker' AS kind,
         CASE technology_broker WHEN 'Human' THEN 11 ELSE 12 END AS ord,
         system, station, distance_to_arrival_ls, x, y, z
  FROM {{MODEL}}.station_service
  WHERE is_listed AND technology_broker IS NOT NULL AND x IS NOT NULL
  UNION ALL
  SELECT material_trader || ' material trader',
         CASE material_trader WHEN 'Raw' THEN 13 WHEN 'Manufactured' THEN 14 ELSE 15 END,
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

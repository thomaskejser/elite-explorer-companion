SELECT DISTINCT s.region
FROM staging.klightspeed_region_map s
WHERE s.region IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM main.region r WHERE r.region = s.region OR r.region = 'The ' || s.region)
ORDER BY 1;

SELECT t.region_id, t.region
FROM main.region t
WHERE NOT EXISTS (SELECT 1 FROM transform.region s WHERE s.region_id = t.region_id)
ORDER BY t.region_id;

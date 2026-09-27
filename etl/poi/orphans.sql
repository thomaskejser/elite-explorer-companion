SELECT t.poi_id, t.poi
FROM main.poi t
WHERE NOT EXISTS (SELECT 1 FROM transform.poi s WHERE s.poi = t.poi)
ORDER BY t.poi_id;

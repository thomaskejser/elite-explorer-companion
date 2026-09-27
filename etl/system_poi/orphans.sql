SELECT t.system_id, t.poi_id, t.system
FROM main.system_poi t
WHERE NOT EXISTS (SELECT 1 FROM transform.system_poi s
                  WHERE s.system_id = t.system_id AND s.poi_id = t.poi_id)
ORDER BY t.system_id, t.poi_id;

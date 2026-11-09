SELECT t.system_id, t.body, t.poi_id
FROM main.body_poi t
WHERE NOT EXISTS (SELECT 1 FROM transform.body_poi s
                  WHERE s.system_id = t.system_id AND s.body = t.body AND s.poi_id = t.poi_id)
ORDER BY t.system_id, t.body, t.poi_id;

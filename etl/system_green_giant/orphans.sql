SELECT count(*)
FROM main.system_green_giant t
WHERE NOT EXISTS (SELECT 1 FROM transform.system_green_giant s WHERE s.system_id = t.system_id AND s.body = t.body);

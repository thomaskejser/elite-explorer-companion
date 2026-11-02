SELECT t.body_id, t.type, t.body
FROM main.body t
WHERE NOT EXISTS (SELECT 1 FROM transform.body s WHERE s.type = t.type AND s.body = t.body)
ORDER BY t.body_id;

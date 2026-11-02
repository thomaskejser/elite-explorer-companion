SELECT count(*)
FROM main.system_exobio t
WHERE NOT EXISTS (SELECT 1 FROM transform.system_exobio s WHERE s.system_id = t.system_id);

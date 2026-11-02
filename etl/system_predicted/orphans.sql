SELECT count(*)
FROM main.system_predicted t
WHERE NOT EXISTS (SELECT 1 FROM transform.system_predicted s WHERE s.system = t.system);

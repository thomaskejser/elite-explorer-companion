DELETE FROM main.system_unfound t
WHERE NOT EXISTS (SELECT 1 FROM transform.system_unfound s WHERE s.system = t.system);

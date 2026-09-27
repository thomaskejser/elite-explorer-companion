SELECT t.type, count(*) AS names
FROM main.system_catalog t
WHERE NOT EXISTS (SELECT 1 FROM transform.system_catalog s WHERE s.system = t.system)
GROUP BY 1
ORDER BY 2 DESC;

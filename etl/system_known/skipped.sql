SELECT sector_name, count(*) AS systems
FROM transform.system_known_source
WHERE sector_id IS NULL
GROUP BY 1
ORDER BY 2 DESC
LIMIT 10;

SELECT sector_id, count(*) AS systems
FROM transform.system_known
GROUP BY sector_id
ORDER BY sector_id;

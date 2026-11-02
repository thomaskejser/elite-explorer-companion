SELECT t.sector, t.sector_id, s.sector_id AS published
FROM main.sector t
JOIN transform.sector s ON s.sector = t.sector
WHERE t.sector_id IS DISTINCT FROM s.sector_id
ORDER BY t.sector;

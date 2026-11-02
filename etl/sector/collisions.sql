SELECT s.sector, s.sector_id, k.sector AS holder
FROM transform.sector s
JOIN main.sector k ON k.sector_id = s.sector_id
WHERE NOT EXISTS (SELECT 1 FROM main.sector t WHERE t.sector = s.sector)
ORDER BY s.sector;

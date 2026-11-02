SELECT t.sector_id, t.sector
FROM main.sector t
WHERE t.sector_id <> 0
  AND NOT EXISTS (SELECT 1 FROM transform.sector s WHERE s.sector = t.sector)
ORDER BY t.sector;

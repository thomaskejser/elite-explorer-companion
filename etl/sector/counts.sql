SELECT
  (SELECT count(*) FROM transform.sector s
   WHERE NOT EXISTS (SELECT 1 FROM main.sector t WHERE t.sector = s.sector)
     AND NOT EXISTS (SELECT 1 FROM main.sector k WHERE k.sector_id = s.sector_id)),
  0;

MERGE INTO main.sector AS t
USING (SELECT * FROM transform.sector s
       WHERE NOT EXISTS (SELECT 1 FROM main.sector k WHERE k.sector_id = s.sector_id)) AS s
ON t.sector = s.sector
WHEN NOT MATCHED
    THEN INSERT (sector_id, sector, x, y, z, radius, is_crafted)
         VALUES (s.sector_id, s.sector, s.x, s.y, s.z, s.radius, s.is_crafted);

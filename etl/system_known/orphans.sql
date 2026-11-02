SELECT t.system_id, t.sector_id, t.system_in_sector
FROM main.system_known t
WHERE NOT EXISTS (SELECT 1 FROM transform.system_known s
                  WHERE s.system_id = t.system_id)
ORDER BY t.system_id
LIMIT 20;

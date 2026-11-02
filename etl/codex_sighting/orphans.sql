SELECT count(*)
FROM main.codex_sighting t
WHERE NOT EXISTS (SELECT 1 FROM transform.codex_sighting s
                  WHERE s.codex = t.codex AND s.region_id = t.region_id AND s.sector_id = t.sector_id);

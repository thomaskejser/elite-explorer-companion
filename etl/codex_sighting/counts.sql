SELECT
  (SELECT count(*) FROM transform.codex_sighting s
   WHERE NOT EXISTS (SELECT 1 FROM main.codex_sighting t
                     WHERE t.codex = s.codex AND t.region_id = s.region_id AND t.sector_id = s.sector_id)),
  (SELECT count(*) FROM main.codex_sighting t JOIN transform.codex_sighting s
     ON t.codex = s.codex AND t.region_id = s.region_id AND t.sector_id = s.sector_id
   WHERE t.entry          IS DISTINCT FROM s.entry
      OR t.category       IS DISTINCT FROM s.category
      OR t.systems        IS DISTINCT FROM s.systems
      OR t.system_id      IS DISTINCT FROM s.system_id
      OR t.system         IS DISTINCT FROM s.system
      OR t.x              IS DISTINCT FROM s.x
      OR t.y              IS DISTINCT FROM s.y
      OR t.z              IS DISTINCT FROM s.z
      OR t.first_reported IS DISTINCT FROM s.first_reported
      OR t.last_reported  IS DISTINCT FROM s.last_reported);

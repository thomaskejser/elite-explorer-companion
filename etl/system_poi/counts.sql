SELECT
  (SELECT count(*) FROM transform.system_poi s
   WHERE NOT EXISTS (SELECT 1 FROM main.system_poi t
                     WHERE t.system_id = s.system_id AND t.poi_id = s.poi_id)),
  (SELECT count(*) FROM main.system_poi t JOIN transform.system_poi s
     ON t.system_id = s.system_id AND t.poi_id = s.poi_id
   WHERE t.system IS DISTINCT FROM s.system
      OR t.sector IS DISTINCT FROM s.sector
      OR t.x      IS DISTINCT FROM s.x
      OR t.y      IS DISTINCT FROM s.y
      OR t.z      IS DISTINCT FROM s.z);

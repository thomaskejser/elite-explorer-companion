SELECT
  (SELECT count(*) FROM transform.body_poi s
   WHERE NOT EXISTS (SELECT 1 FROM main.body_poi t
                     WHERE t.system_id = s.system_id AND t.body = s.body AND t.poi_id = s.poi_id)),
  (SELECT count(*) FROM main.body_poi t JOIN transform.body_poi s
     ON t.system_id = s.system_id AND t.body = s.body AND t.poi_id = s.poi_id
   WHERE t.source IS DISTINCT FROM s.source);

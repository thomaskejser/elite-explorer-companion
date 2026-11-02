SELECT
  (SELECT count(*) FROM main.system_known t JOIN staging.poi_sys s USING (system_id)
   WHERE t.poi_id IS DISTINCT FROM s.poi_id),
  (SELECT count(*) FROM main.system_known t
   WHERE t.poi_id IS NOT NULL
     AND NOT EXISTS (SELECT 1 FROM staging.poi_sys s WHERE s.system_id = t.system_id));

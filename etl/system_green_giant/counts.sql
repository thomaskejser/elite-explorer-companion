SELECT
  (SELECT count(*) FROM transform.system_green_giant s
   WHERE NOT EXISTS (SELECT 1 FROM main.system_green_giant t WHERE t.system_id = s.system_id AND t.body = s.body)),
  (SELECT count(*) FROM main.system_green_giant t JOIN transform.system_green_giant s USING (system_id, body)
   WHERE t.system         IS DISTINCT FROM s.system
      OR t.class          IS DISTINCT FROM s.class
      OR t.surface_temp_k IS DISTINCT FROM s.surface_temp_k
      OR t.verdict        IS DISTINCT FROM s.verdict
      OR t.x              IS DISTINCT FROM s.x
      OR t.y              IS DISTINCT FROM s.y
      OR t.z              IS DISTINCT FROM s.z);

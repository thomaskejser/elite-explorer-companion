SELECT
  (SELECT count(*) FROM transform.region_map s
   WHERE NOT EXISTS (SELECT 1 FROM main.region_map t WHERE t.z_row = s.z_row AND t.x_start = s.x_start)),
  (SELECT count(*) FROM main.region_map t JOIN transform.region_map s USING (z_row, x_start)
   WHERE t.length IS DISTINCT FROM s.length OR t.region_id IS DISTINCT FROM s.region_id);

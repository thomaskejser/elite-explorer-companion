SELECT
  (SELECT count(*) FROM transform.system_known s
   WHERE NOT EXISTS (SELECT 1 FROM main.system_known t
                     WHERE t.system_id = s.system_id)),
  (SELECT count(*) FROM main.system_known t JOIN transform.system_known s
          USING (system_id)
   WHERE (s.body_count IS NOT NULL AND t.body_count IS DISTINCT FROM s.body_count)
      OR (s.primary_star_body_id IS NOT NULL
          AND t.primary_star_body_id IS DISTINCT FROM s.primary_star_body_id)
      OR (t.region_id IS NULL AND s.region_id IS NOT NULL)
      OR t.x IS DISTINCT FROM s.x
      OR t.y IS DISTINCT FROM s.y
      OR t.z IS DISTINCT FROM s.z);

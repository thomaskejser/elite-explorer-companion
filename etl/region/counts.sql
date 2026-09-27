SELECT
  (SELECT count(*) FROM transform.region s
   WHERE NOT EXISTS (SELECT 1 FROM main.region t WHERE t.region_id = s.region_id)),
  (SELECT count(*) FROM main.region t JOIN transform.region s USING (region_id)
   WHERE t.region IS DISTINCT FROM s.region);

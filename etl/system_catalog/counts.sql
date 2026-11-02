SELECT
  (SELECT count(*) FROM transform.system_catalog s
   WHERE NOT EXISTS (SELECT 1 FROM main.system_catalog t WHERE t.system = s.system)),
  (SELECT count(*) FROM main.system_catalog t JOIN transform.system_catalog s USING (system)
   WHERE t.type IS DISTINCT FROM s.type
      OR t.designation IS DISTINCT FROM s.designation);

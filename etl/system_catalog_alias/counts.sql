SELECT
  (SELECT count(*) FROM transform.system_catalog_alias s
   WHERE NOT EXISTS (SELECT 1 FROM main.system_catalog_alias t
                     WHERE t.system_a = s.system_a AND t.system_b = s.system_b)),
  (SELECT count(*) FROM main.system_catalog_alias t
   JOIN transform.system_catalog_alias s USING (system_a, system_b)
   WHERE t.source IS DISTINCT FROM s.source);

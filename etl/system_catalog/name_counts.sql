SELECT
  count(*) FILTER (WHERE s.system_id IS NOT NULL
                     AND t.system_id IS DISTINCT FROM s.system_id),
  count(*) FILTER (WHERE s.system_id IS NULL AND t.system_id IS NOT NULL),
  (SELECT count(*) FROM transform.system_catalog_name WHERE candidates > 1)
FROM main.system_catalog t
JOIN transform.system_catalog_name s USING (system);

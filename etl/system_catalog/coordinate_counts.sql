SELECT count(*)
FROM main.system_catalog t
JOIN transform.system_catalog_coordinate s USING (system)
WHERE t.missing_coordinate IS DISTINCT FROM s.missing_coordinate;

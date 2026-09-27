INSERT INTO transform.system_catalog_placed (name)
SELECT DISTINCT n.other
FROM (SELECT system_a AS name, system_b AS other FROM main.system_catalog_alias
      UNION ALL
      SELECT system_b AS name, system_a AS other FROM main.system_catalog_alias) n
JOIN transform.system_catalog_placed p ON p.name = n.name
WHERE NOT EXISTS (SELECT 1 FROM transform.system_catalog_placed q WHERE q.name = n.other);

DELETE FROM main.system_catalog_alias t
WHERE NOT EXISTS (SELECT 1 FROM transform.system_catalog_alias s
                  WHERE s.system_a = t.system_a AND s.system_b = t.system_b);

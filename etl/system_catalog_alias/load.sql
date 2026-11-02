MERGE INTO main.system_catalog_alias AS t
USING transform.system_catalog_alias AS s
   ON t.system_a = s.system_a AND t.system_b = s.system_b
WHEN MATCHED AND t.source IS DISTINCT FROM s.source
    THEN UPDATE SET source = s.source
WHEN NOT MATCHED
    THEN INSERT (system_a, system_b, source) VALUES (s.system_a, s.system_b, s.source);

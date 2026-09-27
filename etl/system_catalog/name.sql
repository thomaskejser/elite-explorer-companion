MERGE INTO main.system_catalog AS t
USING transform.system_catalog_name AS s ON t.system = s.system
WHEN MATCHED AND t.system_id IS DISTINCT FROM s.system_id
    THEN UPDATE SET system_id = s.system_id;

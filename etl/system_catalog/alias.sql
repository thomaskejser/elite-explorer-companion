MERGE INTO main.system_catalog AS t
USING transform.system_catalog_agreed AS s ON t.system = s.system
WHEN MATCHED AND t.system_id IS NULL
    THEN UPDATE SET system_id = s.system_id;

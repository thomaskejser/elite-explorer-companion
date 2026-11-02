MERGE INTO main.system_catalog AS t
USING (
    SELECT a.system, a.system_id
    FROM staging.commander_alias a
    WHERE a.system_id IS NOT NULL
      AND EXISTS (SELECT 1 FROM main.system_known k WHERE k.system_id = a.system_id)
) AS s ON t.system = s.system
WHEN MATCHED AND t.system_id IS NULL
    THEN UPDATE SET system_id = s.system_id;

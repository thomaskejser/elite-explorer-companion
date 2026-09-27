MERGE INTO main.system_catalog AS t
USING transform.system_catalog AS s ON t.system = s.system
WHEN MATCHED AND (t.type IS DISTINCT FROM s.type
               OR t.designation IS DISTINCT FROM s.designation)
    THEN UPDATE SET type = s.type, designation = s.designation
WHEN NOT MATCHED
    THEN INSERT (system, type, designation, system_id, missing_coordinate)
         VALUES (s.system, s.type, s.designation, NULL, NULL);

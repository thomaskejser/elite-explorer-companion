MERGE INTO main.system_catalog AS t
USING transform.system_catalog_coordinate AS s ON t.system = s.system
WHEN MATCHED AND t.missing_coordinate IS DISTINCT FROM s.missing_coordinate
    THEN UPDATE SET missing_coordinate = s.missing_coordinate;

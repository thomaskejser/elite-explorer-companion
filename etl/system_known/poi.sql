MERGE INTO main.system_known AS t
USING staging.poi_sys AS s ON t.system_id = s.system_id
WHEN MATCHED AND t.poi_id IS DISTINCT FROM s.poi_id THEN UPDATE SET poi_id = s.poi_id
WHEN NOT MATCHED BY SOURCE AND t.poi_id IS NOT NULL THEN UPDATE SET poi_id = NULL;

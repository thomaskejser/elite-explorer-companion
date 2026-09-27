MERGE INTO main.system_known AS t
USING staging.poi_sys AS s ON t.system_id = s.system_id
WHEN MATCHED AND t.id_poi IS DISTINCT FROM s.poi_id THEN UPDATE SET id_poi = s.poi_id
WHEN NOT MATCHED BY SOURCE AND t.id_poi IS NOT NULL THEN UPDATE SET id_poi = NULL;

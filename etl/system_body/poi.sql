MERGE INTO main.system_body AS t
USING staging.poi_body_merge AS s
ON t.system_id = s.system_id AND t.system_body = s.body_suffix AND t.body_no = s.body_no
WHEN MATCHED AND t.id_poi IS DISTINCT FROM s.poi_id THEN UPDATE SET id_poi = s.poi_id
WHEN NOT MATCHED THEN INSERT
    (system_id, body_no, body_id, system_body, is_primary, discovered_time,
     solar_masses, earth_masses, is_terraformable, source, id_poi)
VALUES
    (s.system_id, s.body_no, NULL, s.body_suffix, false, NULL,
     NULL, NULL, NULL, 'canonn_codex', s.poi_id)
WHEN NOT MATCHED BY SOURCE AND t.id_poi IS NOT NULL THEN UPDATE SET id_poi = NULL;

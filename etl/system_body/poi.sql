MERGE INTO main.system_body AS t
USING staging.poi_body_merge AS s
ON t.system_id = s.system_id AND t.system_body = s.body_suffix AND t.body_no = s.body_no
WHEN MATCHED AND t.poi_id IS DISTINCT FROM s.poi_id THEN UPDATE SET poi_id = s.poi_id
WHEN NOT MATCHED THEN INSERT
    (system_id, body_no, body_id, system_body, is_primary, discovered_time,
     solar_masses, earth_masses, is_terraformable, source, poi_id)
VALUES
    (s.system_id, s.body_no, NULL, s.body_suffix, false, NULL,
     NULL, NULL, NULL, 'canonn_codex', s.poi_id)
WHEN NOT MATCHED BY SOURCE AND t.poi_id IS NOT NULL THEN UPDATE SET poi_id = NULL;

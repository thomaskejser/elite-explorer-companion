MERGE INTO main.body_poi AS t
USING transform.body_poi AS s
   ON t.system_id = s.system_id AND t.body = s.body AND t.poi_id = s.poi_id
WHEN MATCHED AND t.source IS DISTINCT FROM s.source
    THEN UPDATE SET source = s.source
WHEN NOT MATCHED
    THEN INSERT (system_id, body, poi_id, source)
         VALUES (s.system_id, s.body, s.poi_id, s.source);

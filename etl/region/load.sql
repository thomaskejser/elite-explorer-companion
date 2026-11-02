MERGE INTO main.region AS t
USING transform.region AS s ON t.region_id = s.region_id
WHEN MATCHED AND t.region IS DISTINCT FROM s.region THEN UPDATE SET region = s.region
WHEN NOT MATCHED THEN INSERT (region_id, region) VALUES (s.region_id, s.region);

MERGE INTO main.region_map AS t
USING transform.region_map AS s ON t.z_row = s.z_row AND t.x_start = s.x_start
WHEN MATCHED AND (t.length IS DISTINCT FROM s.length OR t.region_id IS DISTINCT FROM s.region_id)
    THEN UPDATE SET length = s.length, region_id = s.region_id
WHEN NOT MATCHED
    THEN INSERT (z_row, x_start, length, region_id) VALUES (s.z_row, s.x_start, s.length, s.region_id);

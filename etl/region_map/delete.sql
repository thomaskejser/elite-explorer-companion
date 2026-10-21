DELETE FROM main.region_map t
WHERE NOT EXISTS (SELECT 1 FROM transform.region_map s WHERE s.z_row = t.z_row AND s.x_start = t.x_start);

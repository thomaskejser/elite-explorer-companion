MERGE INTO main.system_known AS t
USING (SELECT * FROM transform.system_known
       WHERE sector_id >= ? AND sector_id < ?) AS s
ON t.system_id = s.system_id
WHEN MATCHED AND (
       (s.body_count IS NOT NULL AND t.body_count IS DISTINCT FROM s.body_count)
    OR (s.primary_star_body_id IS NOT NULL
        AND t.primary_star_body_id IS DISTINCT FROM s.primary_star_body_id)
    OR (t.region_id IS NULL AND s.region_id IS NOT NULL)
    OR t.x IS DISTINCT FROM s.x
    OR t.y IS DISTINCT FROM s.y
    OR t.z IS DISTINCT FROM s.z)
THEN UPDATE SET
    body_count           = coalesce(s.body_count, t.body_count),
    primary_star_body_id = coalesce(s.primary_star_body_id, t.primary_star_body_id),
    region_id            = coalesce(t.region_id, s.region_id),
    x = s.x, y = s.y, z = s.z
WHEN NOT MATCHED THEN INSERT
    (system_id, sector_id, system_in_sector, cube_id, mass_code, sub_cube_id,
     boxel_index, region_id, primary_star_body_id, body_count, x, y, z, first_seen)
VALUES
    (s.system_id, s.sector_id, s.system_in_sector, s.cube_id, s.mass_code,
     s.sub_cube_id, s.boxel_index, s.region_id, s.primary_star_body_id,
     s.body_count, s.x, s.y, s.z, ?);

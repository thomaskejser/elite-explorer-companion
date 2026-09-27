INSERT INTO transform.system_known
SELECT system_id, sector_id, system_in_sector, cube_id, mass_code, sub_cube_id,
       boxel_index, region_id, primary_star_body_id, body_count, x, y, z, source
FROM transform.system_known_source
WHERE sector_id IS NOT NULL
  AND hash(system_id) % ? = ?;

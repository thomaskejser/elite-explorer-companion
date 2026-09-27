MERGE INTO main.system_poi AS t
USING transform.system_poi AS s
   ON t.system_id = s.system_id AND t.poi_id = s.poi_id
WHEN MATCHED AND (t.system IS DISTINCT FROM s.system
               OR t.sector IS DISTINCT FROM s.sector
               OR t.x      IS DISTINCT FROM s.x
               OR t.y      IS DISTINCT FROM s.y
               OR t.z      IS DISTINCT FROM s.z)
    THEN UPDATE SET system = s.system, sector = s.sector,
                    x = s.x, y = s.y, z = s.z
WHEN NOT MATCHED
    THEN INSERT (system_id, poi_id, system, sector, x, y, z)
         VALUES (s.system_id, s.poi_id, s.system, s.sector, s.x, s.y, s.z);

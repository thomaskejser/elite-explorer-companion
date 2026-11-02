MERGE INTO main.codex_sighting AS t
USING transform.codex_sighting AS s
   ON t.codex = s.codex AND t.region_id = s.region_id AND t.sector_id = s.sector_id
WHEN MATCHED AND (t.entry          IS DISTINCT FROM s.entry
               OR t.category       IS DISTINCT FROM s.category
               OR t.systems        IS DISTINCT FROM s.systems
               OR t.system_id      IS DISTINCT FROM s.system_id
               OR t.system         IS DISTINCT FROM s.system
               OR t.x              IS DISTINCT FROM s.x
               OR t.y              IS DISTINCT FROM s.y
               OR t.z              IS DISTINCT FROM s.z
               OR t.first_reported IS DISTINCT FROM s.first_reported
               OR t.last_reported  IS DISTINCT FROM s.last_reported)
    THEN UPDATE SET entry = s.entry, category = s.category, systems = s.systems,
                    system_id = s.system_id, system = s.system, x = s.x, y = s.y, z = s.z,
                    first_reported = s.first_reported, last_reported = s.last_reported
WHEN NOT MATCHED
    THEN INSERT (codex, region_id, sector_id, entry, category, systems, system_id, system,
                 x, y, z, first_reported, last_reported)
         VALUES (s.codex, s.region_id, s.sector_id, s.entry, s.category, s.systems, s.system_id,
                 s.system, s.x, s.y, s.z, s.first_reported, s.last_reported);

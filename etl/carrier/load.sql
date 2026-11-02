MERGE INTO main.carrier AS t
USING transform.carrier AS s ON t.callsign = s.callsign
WHEN MATCHED AND (t.carrier_name IS DISTINCT FROM s.carrier_name
               OR t.last_moved   IS DISTINCT FROM s.last_moved
               OR t.last_seen    IS DISTINCT FROM s.last_seen
               OR t.has_universal_cartographics
                    IS DISTINCT FROM s.has_universal_cartographics
               OR t.is_reliable  IS DISTINCT FROM s.is_reliable
               OR t.system_id    IS DISTINCT FROM s.system_id)
    THEN UPDATE SET carrier_name = s.carrier_name, last_moved = s.last_moved,
                    last_seen = s.last_seen,
                    has_universal_cartographics = s.has_universal_cartographics,
                    is_reliable = s.is_reliable, system_id = s.system_id
WHEN NOT MATCHED
    THEN INSERT (callsign, carrier_name, last_moved, last_seen,
                 has_universal_cartographics, is_reliable, system_id)
         VALUES (s.callsign, s.carrier_name, s.last_moved, s.last_seen,
                 s.has_universal_cartographics, s.is_reliable, s.system_id);

MERGE INTO main.carrier_position AS t
USING transform.carrier_position AS s ON t.callsign = s.callsign
WHEN MATCHED AND (t.system IS DISTINCT FROM s.system
               OR t.x      IS DISTINCT FROM s.x
               OR t.y      IS DISTINCT FROM s.y
               OR t.z      IS DISTINCT FROM s.z)
    THEN UPDATE SET system = s.system, x = s.x, y = s.y, z = s.z
WHEN NOT MATCHED
    THEN INSERT (callsign, system, x, y, z)
         VALUES (s.callsign, s.system, s.x, s.y, s.z);

MERGE INTO main.system_green_giant AS t
USING transform.system_green_giant AS s ON t.system_id = s.system_id AND t.body = s.body
WHEN MATCHED AND (t.system         IS DISTINCT FROM s.system
               OR t.class          IS DISTINCT FROM s.class
               OR t.surface_temp_k IS DISTINCT FROM s.surface_temp_k
               OR t.verdict        IS DISTINCT FROM s.verdict
               OR t.x              IS DISTINCT FROM s.x
               OR t.y              IS DISTINCT FROM s.y
               OR t.z              IS DISTINCT FROM s.z)
THEN UPDATE SET system         = s.system,
                class          = s.class,
                surface_temp_k = s.surface_temp_k,
                verdict        = s.verdict,
                x              = s.x,
                y              = s.y,
                z              = s.z
WHEN NOT MATCHED THEN INSERT
    (system_id, body, system, class, surface_temp_k, verdict, x, y, z)
VALUES
    (s.system_id, s.body, s.system, s.class, s.surface_temp_k, s.verdict, s.x, s.y, s.z);

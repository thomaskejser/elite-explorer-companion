MERGE INTO main.system_phenomenon AS t
USING transform.system_phenomenon AS s
   ON t.system_id = s.system_id AND t.phenomenon = s.phenomenon
WHEN MATCHED AND (t.kinds          IS DISTINCT FROM s.kinds
               OR t.observations   IS DISTINCT FROM s.observations
               OR t.first_reported IS DISTINCT FROM s.first_reported
               OR t.last_reported  IS DISTINCT FROM s.last_reported
               OR t.from_canonn    IS DISTINCT FROM s.from_canonn
               OR t.from_edsm      IS DISTINCT FROM s.from_edsm
               OR t.from_gec       IS DISTINCT FROM s.from_gec)
    THEN UPDATE SET kinds = s.kinds, observations = s.observations,
                    first_reported = s.first_reported, last_reported = s.last_reported,
                    from_canonn = s.from_canonn, from_edsm = s.from_edsm,
                    from_gec = s.from_gec
WHEN NOT MATCHED
    THEN INSERT (system_phenomenon_id, system_id, phenomenon, kinds, observations,
                 first_reported, last_reported, from_canonn, from_edsm, from_gec)
         VALUES (s.system_phenomenon_id, s.system_id, s.phenomenon, s.kinds,
                 s.observations, s.first_reported, s.last_reported,
                 s.from_canonn, s.from_edsm, s.from_gec);

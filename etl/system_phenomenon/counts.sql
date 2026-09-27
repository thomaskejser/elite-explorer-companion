SELECT
  (SELECT count(*) FROM transform.system_phenomenon s
   WHERE NOT EXISTS (SELECT 1 FROM main.system_phenomenon t
                     WHERE t.system_id = s.system_id AND t.phenomenon = s.phenomenon)),
  (SELECT count(*) FROM main.system_phenomenon t JOIN transform.system_phenomenon s
     ON t.system_id = s.system_id AND t.phenomenon = s.phenomenon
   WHERE t.kinds          IS DISTINCT FROM s.kinds
      OR t.observations   IS DISTINCT FROM s.observations
      OR t.first_reported IS DISTINCT FROM s.first_reported
      OR t.last_reported  IS DISTINCT FROM s.last_reported
      OR t.from_canonn    IS DISTINCT FROM s.from_canonn
      OR t.from_edsm      IS DISTINCT FROM s.from_edsm
      OR t.from_gec       IS DISTINCT FROM s.from_gec);

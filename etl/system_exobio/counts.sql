SELECT
  (SELECT count(*) FROM transform.system_exobio s
   WHERE NOT EXISTS (SELECT 1 FROM main.system_exobio t WHERE t.system_id = s.system_id)),
  (SELECT count(*) FROM main.system_exobio t JOIN transform.system_exobio s USING (system_id)
   WHERE t.system           IS DISTINCT FROM s.system
      OR t.x                IS DISTINCT FROM s.x
      OR t.y                IS DISTINCT FROM s.y
      OR t.z                IS DISTINCT FROM s.z
      OR t.candidate_bodies IS DISTINCT FROM s.candidate_bodies
      OR t.unmapped_bodies  IS DISTINCT FROM s.unmapped_bodies
      OR t.worked_bodies    IS DISTINCT FROM s.worked_bodies
      OR t.cr_expected      IS DISTINCT FROM s.cr_expected
      OR t.best_body        IS DISTINCT FROM s.best_body
      OR t.best_cr          IS DISTINCT FROM s.best_cr
      OR t.best_species     IS DISTINCT FROM s.best_species
      OR t.last_reported    IS DISTINCT FROM s.last_reported);

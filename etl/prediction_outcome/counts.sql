SELECT
  (SELECT count(*) FROM transform.prediction_outcome s
   WHERE NOT EXISTS (SELECT 1 FROM main.prediction_outcome t
                     WHERE t.system = s.system AND t.is_catalog = s.is_catalog)),
  (SELECT count(*) FROM main.prediction_outcome t
   JOIN transform.prediction_outcome s ON t.system = s.system AND t.is_catalog = s.is_catalog
   WHERE t.system_id IS DISTINCT FROM s.system_id
      OR t.first_seen IS DISTINCT FROM s.first_seen OR t.revealed_by IS DISTINCT FROM s.revealed_by
      OR t.primary_code IS DISTINCT FROM s.primary_code
      OR t.surveyed_bodies IS DISTINCT FROM s.surveyed_bodies
      OR t.catalogue_bodies IS DISTINCT FROM s.catalogue_bodies
      OR t.found_bh IS DISTINCT FROM s.found_bh OR t.found_wr IS DISTINCT FROM s.found_wr
      OR t.found_neutron IS DISTINCT FROM s.found_neutron OR t.found_wd IS DISTINCT FROM s.found_wd
      OR t.found_herbig IS DISTINCT FROM s.found_herbig OR t.found_otype IS DISTINCT FROM s.found_otype
      OR t.found_supergiant IS DISTINCT FROM s.found_supergiant);

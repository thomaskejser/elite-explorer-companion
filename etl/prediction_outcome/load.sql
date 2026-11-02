MERGE INTO main.prediction_outcome AS t
USING transform.prediction_outcome AS s ON t.system = s.system AND t.is_catalog = s.is_catalog
WHEN MATCHED AND (t.system_id IS DISTINCT FROM s.system_id
      OR t.first_seen IS DISTINCT FROM s.first_seen OR t.revealed_by IS DISTINCT FROM s.revealed_by
      OR t.primary_code IS DISTINCT FROM s.primary_code
      OR t.surveyed_bodies IS DISTINCT FROM s.surveyed_bodies
      OR t.catalogue_bodies IS DISTINCT FROM s.catalogue_bodies
      OR t.found_bh IS DISTINCT FROM s.found_bh OR t.found_wr IS DISTINCT FROM s.found_wr
      OR t.found_neutron IS DISTINCT FROM s.found_neutron OR t.found_wd IS DISTINCT FROM s.found_wd
      OR t.found_herbig IS DISTINCT FROM s.found_herbig OR t.found_otype IS DISTINCT FROM s.found_otype
      OR t.found_supergiant IS DISTINCT FROM s.found_supergiant)
    THEN UPDATE SET system_id = s.system_id, first_seen = s.first_seen, revealed_by = s.revealed_by,
                    primary_code = s.primary_code, surveyed_bodies = s.surveyed_bodies,
                    catalogue_bodies = s.catalogue_bodies, found_bh = s.found_bh, found_wr = s.found_wr,
                    found_neutron = s.found_neutron, found_wd = s.found_wd, found_herbig = s.found_herbig,
                    found_otype = s.found_otype, found_supergiant = s.found_supergiant
WHEN NOT MATCHED
    THEN INSERT (system, is_catalog, system_id, sector, mass_code, x, y, z,
                 p_bh, p_wr, p_neutron, p_wd, p_herbig, p_otype, p_supergiant, exp_bodies,
                 predicted_in, recorded_utc, first_seen, revealed_by, primary_code,
                 surveyed_bodies, catalogue_bodies, found_bh, found_wr, found_neutron, found_wd,
                 found_herbig, found_otype, found_supergiant)
         VALUES (s.system, s.is_catalog, s.system_id, s.sector, s.mass_code, s.x, s.y, s.z,
                 s.p_bh, s.p_wr, s.p_neutron, s.p_wd, s.p_herbig, s.p_otype, s.p_supergiant, s.exp_bodies,
                 s.predicted_in, s.recorded_utc, s.first_seen, s.revealed_by, s.primary_code,
                 s.surveyed_bodies, s.catalogue_bodies, s.found_bh, s.found_wr, s.found_neutron, s.found_wd,
                 s.found_herbig, s.found_otype, s.found_supergiant);

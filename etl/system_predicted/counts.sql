SELECT
  (SELECT count(*) FROM transform.system_predicted s
   WHERE NOT EXISTS (SELECT 1 FROM main.system_predicted t WHERE t.system = s.system)),
  (SELECT count(*) FROM main.system_predicted t
   JOIN transform.system_predicted s ON t.system = s.system
   WHERE t.system_id64       IS DISTINCT FROM s.system_id64
      OR t.is_catalog        IS DISTINCT FROM s.is_catalog
      OR t.mass_code         IS DISTINCT FROM s.mass_code
      OR t.sector            IS DISTINCT FROM s.sector
      OR t.boxel             IS DISTINCT FROM s.boxel
      OR t.x                 IS DISTINCT FROM s.x
      OR t.y                 IS DISTINCT FROM s.y
      OR t.z                 IS DISTINCT FROM s.z
      OR t.plane_r           IS DISTINCT FROM s.plane_r
      OR t.r_sgra            IS DISTINCT FROM s.r_sgra
      OR t.dist_sol          IS DISTINCT FROM s.dist_sol
      OR t.p_bh              IS DISTINCT FROM s.p_bh
      OR t.p_wr              IS DISTINCT FROM s.p_wr
      OR t.p_neutron         IS DISTINCT FROM s.p_neutron
      OR t.p_wd              IS DISTINCT FROM s.p_wd
      OR t.p_herbig          IS DISTINCT FROM s.p_herbig
      OR t.p_otype           IS DISTINCT FROM s.p_otype
      OR t.p_supergiant      IS DISTINCT FROM s.p_supergiant
      OR t.exp_bodies        IS DISTINCT FROM s.exp_bodies
      OR t.exp_scan_value_cr IS DISTINCT FROM s.exp_scan_value_cr);

MERGE INTO main.system_predicted AS t
USING transform.system_predicted AS s ON t.system = s.system
WHEN MATCHED AND (
       t.system_id64       IS DISTINCT FROM s.system_id64
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
    OR t.exp_scan_value_cr IS DISTINCT FROM s.exp_scan_value_cr)
THEN UPDATE SET
    system_id64 = s.system_id64,
    is_catalog = s.is_catalog,
    mass_code = s.mass_code,
    sector = s.sector,
    boxel = s.boxel,
    x = s.x,
    y = s.y,
    z = s.z,
    plane_r = s.plane_r,
    r_sgra = s.r_sgra,
    dist_sol = s.dist_sol,
    p_bh = s.p_bh,
    p_wr = s.p_wr,
    p_neutron = s.p_neutron,
    p_wd = s.p_wd,
    p_herbig = s.p_herbig,
    p_otype = s.p_otype,
    p_supergiant = s.p_supergiant,
    exp_bodies = s.exp_bodies,
    exp_scan_value_cr = s.exp_scan_value_cr
WHEN NOT MATCHED THEN INSERT
    (system_predicted_id, system, system_id64, is_catalog, mass_code, sector, boxel,
    x, y, z, plane_r, r_sgra, dist_sol, p_bh, p_wr, p_neutron, p_wd, p_herbig,
    p_otype, p_supergiant, exp_bodies, exp_scan_value_cr)
VALUES
    (s.system_predicted_id, s.system, s.system_id64, s.is_catalog, s.mass_code,
    s.sector, s.boxel, s.x, s.y, s.z, s.plane_r, s.r_sgra, s.dist_sol, s.p_bh,
    s.p_wr, s.p_neutron, s.p_wd, s.p_herbig, s.p_otype, s.p_supergiant,
    s.exp_bodies, s.exp_scan_value_cr);

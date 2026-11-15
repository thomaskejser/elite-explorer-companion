INSERT INTO transform.prediction_source
SELECT system, is_catalog, system_id, sector, mass_code, x, y, z,
       p_bh, p_wr, p_neutron, p_wd, p_herbig, p_otype, p_supergiant, exp_bodies,
       predicted_in
FROM (${sources})
WHERE abs(hash(system)) % ? = ?
QUALIFY row_number() OVER (PARTITION BY system, is_catalog ORDER BY taken DESC) = 1;

MERGE INTO main.system_body AS t
USING (SELECT * FROM transform.system_body WHERE abs((system_id >> 3) % ?) = ?) AS s
ON t.system_id = s.system_id AND t.system_body = s.system_body AND t.body_no = s.body_no
WHEN MATCHED
 AND CASE s.source WHEN 'spansh' THEN 1 WHEN 'edsm' THEN 2 WHEN 'edastro' THEN 3
                   WHEN 'edastro_neutron' THEN 4 WHEN 'edastro_rare' THEN 5 ELSE 7 END
  <= CASE t.source WHEN 'spansh' THEN 1 WHEN 'edsm' THEN 2 WHEN 'edastro' THEN 3
                   WHEN 'edastro_neutron' THEN 4 WHEN 'edastro_rare' THEN 5
                   WHEN 'canonn_codex' THEN 6 ELSE 7 END
 AND (t.body_id          IS DISTINCT FROM coalesce(t.body_id, s.body_id)
   OR t.solar_masses     IS DISTINCT FROM coalesce(s.solar_masses, t.solar_masses)
   OR t.earth_masses     IS DISTINCT FROM coalesce(s.earth_masses, t.earth_masses)
   OR t.is_terraformable IS DISTINCT FROM coalesce(s.is_terraformable, t.is_terraformable)
   OR t.source           IS DISTINCT FROM s.source)
THEN UPDATE SET
    body_id          = coalesce(t.body_id, s.body_id),
    solar_masses     = coalesce(s.solar_masses, t.solar_masses),
    earth_masses     = coalesce(s.earth_masses, t.earth_masses),
    is_terraformable = coalesce(s.is_terraformable, t.is_terraformable),
    source           = s.source
WHEN NOT MATCHED THEN INSERT
    (system_id, body_no, body_id, system_body, is_primary, discovered_time,
     solar_masses, earth_masses, is_terraformable, source)
VALUES
    (s.system_id, s.body_no, s.body_id, s.system_body, s.is_primary,
     s.discovered_time, s.solar_masses, s.earth_masses, s.is_terraformable, s.source);

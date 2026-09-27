WITH s AS (SELECT * FROM transform.system_body WHERE abs((system_id >> 3) % ?) = ?)
SELECT
  (SELECT count(*) FROM s
   WHERE NOT EXISTS (SELECT 1 FROM main.system_body t
                     WHERE t.system_id = s.system_id AND t.system_body = s.system_body
                       AND t.body_no = s.body_no)),
  (SELECT count(*) FROM main.system_body t
   JOIN s ON t.system_id = s.system_id AND t.system_body = s.system_body
         AND t.body_no = s.body_no
   WHERE CASE s.source WHEN 'spansh' THEN 1 WHEN 'edsm' THEN 2 WHEN 'edastro' THEN 3
                       WHEN 'edastro_neutron' THEN 4 WHEN 'edastro_rare' THEN 5 ELSE 7 END
      <= CASE t.source WHEN 'spansh' THEN 1 WHEN 'edsm' THEN 2 WHEN 'edastro' THEN 3
                       WHEN 'edastro_neutron' THEN 4 WHEN 'edastro_rare' THEN 5
                       WHEN 'canonn_codex' THEN 6 ELSE 7 END
     AND (t.body_id          IS DISTINCT FROM coalesce(t.body_id, s.body_id)
       OR t.solar_masses     IS DISTINCT FROM coalesce(s.solar_masses, t.solar_masses)
       OR t.earth_masses     IS DISTINCT FROM coalesce(s.earth_masses, t.earth_masses)
       OR t.is_terraformable IS DISTINCT FROM coalesce(s.is_terraformable, t.is_terraformable)
       OR t.source           IS DISTINCT FROM s.source));

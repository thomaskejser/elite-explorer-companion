SELECT
  (SELECT count(*) FROM src_route s
   WHERE NOT EXISTS (SELECT 1 FROM main.route t
                     WHERE t.route = s.route AND t.hop = s.hop)),
  (SELECT count(*) FROM main.route t
   JOIN src_route s USING (route, hop)
   WHERE t.system     IS DISTINCT FROM s.system
      OR t.x          IS DISTINCT FROM s.x
      OR t.y          IS DISTINCT FROM s.y
      OR t.z          IS DISTINCT FROM s.z
      OR t.hop_ly     IS DISTINCT FROM s.hop_ly
      OR t.to_go_ly   IS DISTINCT FROM s.to_go_ly
      OR t.is_neutron IS DISTINCT FROM s.is_neutron
      OR t.boosted_ly IS DISTINCT FROM s.boosted_ly
      OR t.jumps      IS DISTINCT FROM s.jumps);

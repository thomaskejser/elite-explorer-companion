MERGE INTO main.route AS t
USING src_route AS s ON t.route = s.route AND t.hop = s.hop
WHEN MATCHED AND (t.system     IS DISTINCT FROM s.system
               OR t.x          IS DISTINCT FROM s.x
               OR t.y          IS DISTINCT FROM s.y
               OR t.z          IS DISTINCT FROM s.z
               OR t.hop_ly     IS DISTINCT FROM s.hop_ly
               OR t.to_go_ly   IS DISTINCT FROM s.to_go_ly
               OR t.is_neutron IS DISTINCT FROM s.is_neutron
               OR t.boosted_ly IS DISTINCT FROM s.boosted_ly
               OR t.jumps      IS DISTINCT FROM s.jumps)
    THEN UPDATE SET system = s.system, x = s.x, y = s.y, z = s.z,
                    hop_ly = s.hop_ly, to_go_ly = s.to_go_ly,
                    is_neutron = s.is_neutron, boosted_ly = s.boosted_ly,
                    jumps = s.jumps
WHEN NOT MATCHED
    THEN INSERT (route, hop, system, x, y, z, hop_ly, to_go_ly, is_neutron,
                 boosted_ly, jumps)
         VALUES (s.route, s.hop, s.system, s.x, s.y, s.z, s.hop_ly, s.to_go_ly,
                 s.is_neutron, s.boosted_ly, s.jumps);

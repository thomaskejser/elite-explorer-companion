MERGE INTO main.poi AS t
USING transform.poi AS s ON t.poi = s.poi
WHEN MATCHED AND (t.poi_class     IS DISTINCT FROM s.poi_class
               OR t.poi_family    IS DISTINCT FROM s.poi_family
               OR t.needs_landing IS DISTINCT FROM s.needs_landing
               OR t.sources       IS DISTINCT FROM s.sources
               OR t.systems       IS DISTINCT FROM s.systems
               OR t.bodies        IS DISTINCT FROM s.bodies)
    THEN UPDATE SET poi_class = s.poi_class, poi_family = s.poi_family,
                    needs_landing = s.needs_landing, sources = s.sources,
                    systems = s.systems, bodies = s.bodies
WHEN NOT MATCHED
    THEN INSERT (poi_id, poi, poi_class, poi_family, needs_landing, sources,
                 systems, bodies)
         VALUES (s.poi_id, s.poi, s.poi_class, s.poi_family, s.needs_landing,
                 s.sources, s.systems, s.bodies);

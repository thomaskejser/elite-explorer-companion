SELECT
  (SELECT count(*) FROM transform.poi s
   WHERE NOT EXISTS (SELECT 1 FROM main.poi t WHERE t.poi = s.poi)),
  (SELECT count(*) FROM main.poi t JOIN transform.poi s USING (poi)
   WHERE t.poi_class     IS DISTINCT FROM s.poi_class
      OR t.poi_family    IS DISTINCT FROM s.poi_family
      OR t.needs_landing IS DISTINCT FROM s.needs_landing
      OR t.sources       IS DISTINCT FROM s.sources
      OR t.systems       IS DISTINCT FROM s.systems
      OR t.bodies        IS DISTINCT FROM s.bodies);

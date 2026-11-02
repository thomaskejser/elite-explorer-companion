SELECT c.kind,
       coalesce(c.x, s.x) AS x,
       coalesce(c.y, s.y, 0) AS y,
       coalesce(c.z, s.z) AS z
FROM system_confirmed c
LEFT JOIN system_seen s ON s.system = c.system
WHERE NOT c.visited
  AND c.system NOT IN (SELECT system FROM system_visited)
  AND coalesce(c.x, s.x) IS NOT NULL
  AND coalesce(c.z, s.z) IS NOT NULL

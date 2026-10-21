confirmed AS (
  SELECT system, max(kind) AS kind, max(star_class) AS star_class,
         max(x) AS x, max(y) AS y, max(z) AS z,
         bool_or(is_known) AS is_known
  FROM (
    SELECT s.system,
           CASE {{CLASS_CASE}} ELSE NULL END AS kind,
           s.star_class, s.x, s.y, s.z, s.is_known
    FROM system_seen s
    WHERE s.star_class IN ({{ALL_CLASSES}})
    UNION ALL
    SELECT c.system, c.kind, c.star_class, c.x, c.y, c.z, c.is_known
    FROM system_confirmed c
    WHERE NOT c.visited
  )
  WHERE kind IS NOT NULL
    AND system NOT IN (SELECT system FROM system_visited)
  GROUP BY system
  HAVING bool_or(is_known) IS NOT TRUE
)

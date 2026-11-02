DELETE FROM main.route AS t
WHERE EXISTS (SELECT 1 FROM src_route s WHERE s.route = t.route)
  AND NOT EXISTS (SELECT 1 FROM src_route s
                  WHERE s.route = t.route AND s.hop = t.hop);

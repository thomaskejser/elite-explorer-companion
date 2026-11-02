SELECT t.route, count(*) AS hops, max(t.hop) AS jumps
FROM main.route t
WHERE NOT EXISTS (SELECT 1 FROM src_route s WHERE s.route = t.route)
GROUP BY t.route ORDER BY t.route;

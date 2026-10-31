SELECT strftime(v.first_visited_utc, '%Y-%m-%d') AS day, c.kind, count(*) AS n
FROM system_visited v
JOIN system_confirmed c ON c.system = v.system
WHERE v.first_visited_utc IS NOT NULL
GROUP BY ALL
ORDER BY day, c.kind

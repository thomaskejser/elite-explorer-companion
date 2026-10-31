SELECT strftime(found_date, '%Y-%m-%d') AS day, kind, count(*) AS n
FROM system_confirmed
WHERE found_date IS NOT NULL
GROUP BY ALL
ORDER BY day, kind

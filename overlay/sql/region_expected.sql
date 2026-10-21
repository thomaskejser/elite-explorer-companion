SELECT r.region, count(*) AS n, {{P_SUMS}}
FROM {{MODEL}}.system_predicted p
JOIN {{MODEL}}.sector sc ON sc.sector = p.sector
JOIN {{MODEL}}.region r ON r.region_id = sc.region_id
LEFT JOIN system_visited v ON v.system = p.system
{{SEEN_JOIN}}
WHERE v.system IS NULL AND {{SEEN_CLASS}} IS NULL
GROUP BY r.region_id, r.region
ORDER BY r.region_id

SELECT p.sector, count(*) AS n, coalesce(any_value(k.systems), 0) AS known, {{P_SUMS}}
FROM {{MODEL}}.system_predicted p
JOIN {{MODEL}}.sector sc ON sc.sector = p.sector
LEFT JOIN {{MODEL}}.sector_known k ON k.sector_id = sc.sector_id
LEFT JOIN system_visited v ON v.system = p.system
{{SEEN_JOIN}}
WHERE sc.region_id = ? AND (? OR NOT p.is_catalog) AND v.system IS NULL AND {{SEEN_CLASS}} IS NULL AND p.system NOT IN (SELECT system FROM system_wrong) AND {{UNGATED}}
GROUP BY p.sector
ORDER BY {{P_ORDER}} DESC
LIMIT ?

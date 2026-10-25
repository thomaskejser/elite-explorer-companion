SELECT p.sector, count(*) AS n, coalesce(any_value(k.systems), 0) AS known, {{P_SUMS}}
FROM {{MODEL}}.system_predicted p
JOIN {{MODEL}}.sector sc ON sc.sector = p.sector
LEFT JOIN {{MODEL}}.sector_known k ON k.sector_id = sc.sector_id
{{SEEN_JOIN}}
WHERE sc.region_id = ? AND (? OR NOT p.is_catalog) AND {{OFFERABLE}}
GROUP BY p.sector
ORDER BY {{P_ORDER}} DESC
LIMIT ?

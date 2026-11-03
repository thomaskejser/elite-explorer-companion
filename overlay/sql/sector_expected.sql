WITH conf AS (
    SELECT c.sector, {{CONF_COUNTS}}
    FROM system_confirmed c
    WHERE {{CONF_OPEN}}
    GROUP BY c.sector
)
SELECT p.sector, count(*) AS n, coalesce(any_value(k.systems), 0) AS known, {{P_SUMS}}, NULL::BIGINT AS id, {{CONF_ANY}}
FROM {{MODEL}}.system_predicted p
JOIN {{MODEL}}.sector sc ON sc.sector = p.sector
LEFT JOIN {{MODEL}}.sector_known k ON k.sector_id = sc.sector_id
LEFT JOIN conf f ON f.sector = p.sector
{{SEEN_JOIN}}
WHERE sc.region_id = ? AND (? OR NOT p.is_catalog) AND {{OFFERABLE}}
GROUP BY p.sector
ORDER BY {{P_ORDER}} DESC
LIMIT ?

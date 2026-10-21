WITH predicted AS (
    SELECT sc.region_id, count(*) AS n, {{P_SUMS}}
    FROM {{MODEL}}.system_predicted p
    JOIN {{MODEL}}.sector sc ON sc.sector = p.sector
    LEFT JOIN system_visited v ON v.system = p.system
    {{SEEN_JOIN}}
    WHERE v.system IS NULL AND {{SEEN_CLASS}} IS NULL
    GROUP BY 1
)
SELECT r.region, coalesce(p.n, 0) AS n, coalesce(k.systems, 0) AS known, {{P_COLUMNS_P}}
FROM {{MODEL}}.region r
LEFT JOIN predicted p ON p.region_id = r.region_id
LEFT JOIN {{MODEL}}.region_known k ON k.region_id = r.region_id
ORDER BY r.region_id

SELECT p.is_catalog AS is_cat, count(*) AS n,
       {{P_SUMS}}
FROM {{MODEL}}.system_predicted p
LEFT JOIN system_visited v ON v.system = p.system
{{SEEN_JOIN}}
WHERE p.sector IN (SELECT sc.sector FROM {{MODEL}}.sector sc
                   WHERE sc.region_id = (SELECT sc2.region_id
                                         FROM {{MODEL}}.sector sc2
                                         WHERE sc2.sector = ?))
  AND v.system IS NULL AND {{SEEN_CLASS}} IS NULL
GROUP BY 1

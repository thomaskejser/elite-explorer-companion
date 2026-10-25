SELECT count(*) AS n,
       {{P_SUMS}}
FROM {{MODEL}}.system_predicted p
LEFT JOIN system_visited v ON v.system = p.system
{{SEEN_JOIN}}
WHERE NOT p.is_catalog AND p.sector IN (SELECT sc.sector FROM {{MODEL}}.sector sc WHERE sc.region_id = ?)
  AND v.system IS NULL AND {{SEEN_CLASS}} IS NULL AND p.system NOT IN (SELECT system FROM system_wrong)
  AND {{UNGATED}}

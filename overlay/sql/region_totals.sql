SELECT count(*) AS n,
       {{P_SUMS}}
FROM {{MODEL}}.system_predicted p
{{SEEN_JOIN}}
WHERE NOT p.is_catalog AND p.sector IN (SELECT sc.sector FROM {{MODEL}}.sector sc WHERE sc.region_id = ?)
  AND {{OFFERABLE}}

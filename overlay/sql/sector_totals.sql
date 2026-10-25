SELECT count(*) AS n,
       {{P_SUMS}}
FROM {{MODEL}}.system_predicted p
{{SEEN_JOIN}}
WHERE NOT p.is_catalog AND p.sector = ? AND {{OFFERABLE}}

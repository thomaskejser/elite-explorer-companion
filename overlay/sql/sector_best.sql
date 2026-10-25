SELECT p.system, {{P_PICK}} AS p
FROM {{MODEL}}.system_predicted p
{{SEEN_JOIN}}
WHERE p.sector = ? AND (? OR NOT p.is_catalog)
  AND {{OFFERABLE}}
ORDER BY p DESC NULLS LAST, p.system
LIMIT 1

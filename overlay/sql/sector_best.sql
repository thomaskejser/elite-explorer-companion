SELECT p.system, {{P_PICK}} AS p
FROM {{MODEL}}.system_predicted p
LEFT JOIN system_visited v ON v.system = p.system
{{SEEN_JOIN}}
WHERE p.sector = ? AND (? OR NOT p.is_catalog)
  AND v.system IS NULL AND {{SEEN_CLASS}} IS NULL
  AND p.system NOT IN (SELECT system FROM system_wrong)
  AND {{UNGATED}}
ORDER BY p DESC NULLS LAST, p.system
LIMIT 1

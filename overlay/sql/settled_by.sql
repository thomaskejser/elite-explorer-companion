SELECT p.system, p.sector, p.is_catalog,
       v.system IS NOT NULL AS visited,
       {{SEEN_CLASS}} AS was_classed
FROM {{MODEL}}.system_predicted p
{{SEEN_JOIN}}
WHERE p.system IN (SELECT unnest(string_split(?, chr(31))))
ORDER BY p.sector, p.system

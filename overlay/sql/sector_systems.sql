SELECT p.system,
       nullif(regexp_extract(p.system, {{PROCEDURAL}}, 2), '') AS mass_code,
       {{P_PICK}} AS p,
       sum({{P_PICK}}) OVER () AS expected,
       count(*) OVER () AS listed
FROM {{MODEL}}.system_predicted p
{{SEEN_JOIN}}
WHERE p.sector = ? AND (? OR NOT p.is_catalog)
  AND {{OFFERABLE}}
  AND {{P_PICK}} > 0
ORDER BY p DESC, p.system
LIMIT ?

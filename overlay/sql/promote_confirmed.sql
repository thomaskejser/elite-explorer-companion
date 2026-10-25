INSERT INTO system_confirmed
    (system, kind, star_class, mass_code, x, y, z, system_id, sector,
     was_exact, was_predicted, visited, found_date, is_known)
SELECT src.system,
       src.kind,
       src.star_class,
       nullif(regexp_extract(src.system, '^.* [A-Z][A-Z]-[A-Z] ([a-h])\d', 1), ''),
       src.x, src.y, src.z, src.system_id, src.sector,
       src.x IS NOT NULL AS was_exact,
       p.system IS NOT NULL AS was_predicted,
       EXISTS (SELECT 1 FROM system_visited v WHERE v.system = src.system) AS visited,
       cast(src.first_seen_utc AS DATE) AS found_date,
       src.is_known
FROM (
    SELECT s.system, s.star_class, s.x, s.y, s.z, s.system_id, s.sector,
           s.is_known, s.first_seen_utc,
           CASE {{CLASS_CASE}} ELSE NULL END AS kind
    FROM system_seen s
    WHERE {{ARRIVAL_S}} IN ({{ALL_CLASSES}})
      AND NOT EXISTS (SELECT 1 FROM system_confirmed c WHERE c.system = s.system)
      AND (? OR s.system IN (SELECT unnest(string_split(?, chr(31)))))
) src
LEFT JOIN {{MODEL}}.system_predicted p
       ON p.system = src.system AND p.is_catalog = FALSE
WHERE src.kind IS NOT NULL

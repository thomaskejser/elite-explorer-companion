WITH listed AS (
  SELECT p.system, 'predicted' AS listed_as
  FROM {{MODEL}}.system_predicted p
  WHERE p.sector = ?
  UNION ALL
  SELECT sc.sector || ' ' || n.system_in_sector, 'neutron'
  FROM {{MODEL}}.system_neutron n
  JOIN {{MODEL}}.sector sc ON sc.sector_id = n.sector_id
  WHERE sc.sector = ? AND sc.sector_id <> 0
  UNION ALL
  SELECT p.system, 'POI'
  FROM {{MODEL}}.system_poi p
  WHERE p.sector = ? AND p.sector <> 'crafted'
),
systems AS (
  SELECT system,
         nullif(regexp_extract(system, {{PROCEDURAL}}, 2), '') AS mass_code,
         string_agg(DISTINCT listed_as, ', ' ORDER BY listed_as) AS listed_as
  FROM listed
  GROUP BY system
)
SELECT system, mass_code, listed_as, count(*) OVER () AS listed
FROM systems
ORDER BY mass_code DESC NULLS LAST, system
LIMIT ?

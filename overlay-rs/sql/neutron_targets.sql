WITH nearest AS (
  SELECT k.sector_id, k.system_in_sector, k.mass_code, k.x, k.y, k.z,
         CASE WHEN k.x IS NULL THEN NULL
              ELSE sqrt(pow(k.x - ?, 2) + pow(k.y - ?, 2) + pow(k.z - ?, 2)) END AS dist_ly
  FROM {{MODEL}}.system_neutron k
  WHERE k.x IS NOT NULL
  ORDER BY dist_ly LIMIT ?
),
near AS (
  SELECT CASE WHEN k.sector_id = 0 THEN k.system_in_sector
              ELSE sc.sector || ' ' || k.system_in_sector END AS system,
         k.dist_ly, k.mass_code, k.x, k.y, k.z
  FROM nearest k
  JOIN {{MODEL}}.sector sc ON sc.sector_id = k.sector_id
)
SELECT row_number() OVER (ORDER BY dist_ly) AS rank,
       system,
       '{{NEUTRON_ABBR}}' AS type_label,
       dist_ly, FALSE AS dist_approx,
       {{P_NULLS}},
       {{ROW_NEUTRON}} AS row_grp,
       'Neutron' AS wide_text,
       mass_code AS detail, mass_code,
       NULL::VARCHAR AS boxel,
       x, y, z,
       NULL::DOUBLE AS dist_sol, NULL::VARCHAR AS star_class
FROM near ORDER BY dist_ly LIMIT ?

SELECT CASE WHEN k.sector_id = 0 THEN k.system_in_sector
            ELSE sc.sector || ' ' || k.system_in_sector END AS system,
       k.x, k.y, k.z
FROM {{MODEL}}.system_neutron k
JOIN {{MODEL}}.sector sc ON sc.sector_id = k.sector_id
WHERE k.x IS NOT NULL
  AND sqrt(pow(k.x - ?, 2) + pow(k.y - ?, 2) + pow(k.z - ?, 2))
    + sqrt(pow(k.x - ?, 2) + pow(k.y - ?, 2) + pow(k.z - ?, 2)) <= ?

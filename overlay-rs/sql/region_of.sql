SELECT r.region FROM {{MODEL}}.sector sc
JOIN {{MODEL}}.region r ON r.region_id = sc.region_id
WHERE sc.sector = ?

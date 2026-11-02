SELECT r.region_id, r.region, count(DISTINCT c.codex) AS entries
FROM {{MODEL}}.region r
LEFT JOIN {{MODEL}}.codex_sighting c ON c.region_id = r.region_id
GROUP BY r.region_id, r.region
ORDER BY r.region

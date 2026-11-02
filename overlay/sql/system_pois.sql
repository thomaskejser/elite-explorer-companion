SELECT p.poi,
       p.poi_class || CASE WHEN p.needs_landing THEN ', on a surface' ELSE '' END AS class
FROM {{MODEL}}.system_poi sp
JOIN {{MODEL}}.poi p ON p.poi_id = sp.poi_id
WHERE sp.system_id = ? OR sp.system = ?
GROUP BY p.poi, p.poi_class, p.needs_landing
ORDER BY p.needs_landing DESC, p.poi

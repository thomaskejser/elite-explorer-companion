SELECT p.poi,
       p.poi_class || CASE WHEN p.needs_landing THEN ', on a surface' ELSE '' END AS class,
       coalesce(string_agg(DISTINCT upper(bp.body), ', ' ORDER BY upper(bp.body)), '') AS bodies
FROM {{MODEL}}.system_poi sp
JOIN {{MODEL}}.poi p ON p.poi_id = sp.poi_id
LEFT JOIN {{MODEL}}.body_poi bp ON bp.system_id = sp.system_id AND bp.poi_id = sp.poi_id
WHERE sp.system_id = ? OR sp.system = ?
GROUP BY p.poi, p.poi_class, p.needs_landing
ORDER BY p.needs_landing DESC, p.poi

WITH line AS (
  SELECT ?::DOUBLE ax, ?::DOUBLE ay, ?::DOUBLE az,
         ?::DOUBLE dx, ?::DOUBLE dy, ?::DOUBLE dz, ?::DOUBLE len2),
proj AS (
  SELECT k.x, k.y, k.z, k.sector_id, k.system_in_sector, l.*,
         ((k.x - l.ax) * l.dx + (k.y - l.ay) * l.dy + (k.z - l.az) * l.dz) / l.len2 AS t
  FROM {{MODEL}}.system_neutron k, line l
  WHERE k.x IS NOT NULL)
SELECT CASE WHEN proj.sector_id = 0 THEN proj.system_in_sector
            ELSE sc.sector || ' ' || proj.system_in_sector END AS system,
       proj.x AS x, proj.y AS y, proj.z AS z
FROM proj
JOIN {{MODEL}}.sector sc ON sc.sector_id = proj.sector_id
WHERE proj.t BETWEEN -0.05 AND 1.05
  AND (proj.x - (proj.ax + proj.t * proj.dx)) ** 2
    + (proj.y - (proj.ay + proj.t * proj.dy)) ** 2
    + (proj.z - (proj.az + proj.t * proj.dz)) ** 2 <= ?

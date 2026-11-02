WITH here AS (
    SELECT ?::DOUBLE AS hx, ?::DOUBLE AS hy, ?::DOUBLE AS hz
),
sighted AS (
    SELECT c.codex, c.entry, c.category, c.systems, c.system,
           sqrt(pow(c.x - h.hx, 2) + pow(c.y - h.hy, 2) + pow(c.z - h.hz, 2)) AS ly
    FROM {{MODEL}}.codex_sighting c, here h
    WHERE c.region_id = ?
)
SELECT codex, min(entry) AS entry, min(category) AS category, sum(systems)::BIGINT AS systems,
       arg_min(system, (coalesce(ly, 0), system)) AS nearest, min(ly) AS nearest_ly
FROM sighted
GROUP BY codex
ORDER BY category, entry

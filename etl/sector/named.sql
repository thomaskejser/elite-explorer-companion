INSERT INTO transform.sector (sector_id, sector, x, y, z, radius, is_crafted)
WITH named AS (
    SELECT s.system_id64 AS id64, s.name, s.x, s.y, s.z FROM staging.spansh_system s
    UNION ALL
    SELECT e.id64, e.name, e.coords.x, e.coords.y, e.coords.z FROM staging.edsm_star_system e
    UNION ALL
    SELECT a.id64, a.name, a.coords.x, a.coords.y, a.coords.z FROM staging.edastro_star_system a
),
prefix AS (
    SELECT regexp_extract(name, '^(.*) [A-Z][A-Z]-[A-Z] [a-h]([0-9]+-)?[0-9]+$', 1) AS raw,
           min(sector_id_from_id64(id64)) AS lo_cell,
           max(sector_id_from_id64(id64)) AS hi_cell,
           min(x) AS x0, max(x) AS x1, min(y) AS y0, max(y) AS y1, min(z) AS z0, max(z) AS z1
    FROM named
    WHERE id64 IS NOT NULL AND name IS NOT NULL
      AND x IS NOT NULL AND y IS NOT NULL AND z IS NOT NULL
    GROUP BY 1
),
cleaned AS (
    SELECT clean_sector_name(any_value(raw)) AS sector,
           min(lo_cell) AS lo_cell, max(hi_cell) AS hi_cell,
           min(x0) AS x0, max(x1) AS x1, min(y0) AS y0, max(y1) AS y1, min(z0) AS z0, max(z1) AS z1
    FROM prefix
    WHERE raw <> ''
    GROUP BY clean_sector_name(raw)
),
shaped AS (
    SELECT *,
           lo_cell <> hi_cell OR regexp_matches(sector, '( Sector| Dark Region)$|[0-9]') AS is_crafted
    FROM cleaned
    WHERE sector IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM transform.sector t WHERE t.sector = cleaned.sector)
),
keyed AS (
    SELECT *, CASE WHEN is_crafted THEN sector_id_from_name(sector) ELSE lo_cell END AS sector_id
    FROM shaped
)
SELECT sector_id, sector,
       round((x0 + x1) / 2, 6), round((y0 + y1) / 2, 6), round((z0 + z1) / 2, 6),
       round(((x1 - x0) + (y1 - y0) + (z1 - z0)) / 2, 6),
       is_crafted
FROM keyed k
WHERE NOT EXISTS (SELECT 1 FROM transform.sector t WHERE t.sector_id = k.sector_id)
RETURNING sector;

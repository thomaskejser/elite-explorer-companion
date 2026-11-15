UPDATE main.sector AS t
SET region_id = p.region_id
FROM (
    WITH labelled AS (
        SELECT regexp_extract(a.name, '^(.*) [A-Z][A-Z]-[A-Z] [a-h]([0-9]+-)?[0-9]+$', 1) AS raw,
               a.region AS region_id,
               count(*) AS systems
        FROM staging.edastro_star_system a
        WHERE a.region IS NOT NULL AND a.name IS NOT NULL
        GROUP BY 1, 2
    ),
    voted AS (
        SELECT clean_sector_name(raw) AS sector, region_id, sum(systems) AS systems
        FROM labelled
        WHERE raw <> ''
        GROUP BY 1, 2
    ),
    modal AS (
        SELECT sector, arg_max(region_id, systems * 100 - region_id) AS region_id
        FROM voted
        GROUP BY sector
    ),
    centre AS (
        SELECT s.sector, r.region_id
        FROM main.sector s
        JOIN main.region_map r
          ON r.z_row = CAST(floor((s.z + 24105) * 83 / 4096) AS INTEGER)
         AND CAST(floor((s.x + 49985) * 83 / 4096) AS INTEGER) BETWEEN r.x_start AND r.x_start + r.length - 1
    )
    SELECT s.sector, coalesce(m.region_id, c.region_id) AS region_id
    FROM main.sector s
    LEFT JOIN modal m ON m.sector = s.sector
    LEFT JOIN centre c ON c.sector = s.sector
    WHERE s.region_id IS NULL AND s.sector_id <> 0
) AS p
WHERE t.sector = p.sector AND p.region_id IS NOT NULL
RETURNING t.sector;

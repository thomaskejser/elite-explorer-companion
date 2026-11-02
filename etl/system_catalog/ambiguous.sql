WITH neighbours AS (
    SELECT system_a AS name, system_b AS other FROM main.system_catalog_alias
    UNION ALL
    SELECT system_b AS name, system_a AS other FROM main.system_catalog_alias
),
resolved AS (
    SELECT system AS name, system_id FROM main.system_catalog
    WHERE system_id IS NOT NULL
    UNION ALL
    SELECT system_in_sector AS name, system_id FROM main.system_known
    WHERE sector_id = 0
)
SELECT count(*) FROM (
    SELECT n.name
    FROM neighbours n
    JOIN resolved r ON r.name = n.other
    JOIN main.system_catalog u ON u.system = n.name AND u.system_id IS NULL
    GROUP BY 1
    HAVING count(DISTINCT r.system_id) > 1
);

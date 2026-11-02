SELECT x, y, z FROM (
    SELECT x, y, z, 1 AS pri FROM system_seen WHERE (system = ? OR system_id = ?) AND x IS NOT NULL
    UNION ALL
    SELECT x, y, z, 2 FROM {{MODEL}}.system_predicted WHERE system_id = ? OR (system = ? AND is_catalog)
    UNION ALL
    SELECT x, y, z, 3 FROM {{MODEL}}.station WHERE system = ?
)
ORDER BY pri
LIMIT 1

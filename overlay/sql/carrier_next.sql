WITH target AS (
    SELECT x, y, z FROM (
        SELECT x, y, z, 1 AS pri FROM {{MODEL}}.system_predicted WHERE system = ?
        UNION ALL
        SELECT x, y, z, 2 FROM system_seen WHERE system = ? AND x IS NOT NULL
        UNION ALL
        SELECT x, y, z, 3 FROM {{MODEL}}.station WHERE system = ?
    )
    ORDER BY pri
    LIMIT 1
),
carrier AS (
    SELECT ?::DOUBLE AS cx, ?::DOUBLE AS cy, ?::DOUBLE AS cz
),
candidates AS (
    SELECT system, x, y, z FROM {{MODEL}}.system_predicted WHERE is_catalog
    UNION ALL
    SELECT system, x, y, z FROM {{MODEL}}.station WHERE is_listed AND NOT is_carrier
    UNION ALL
    SELECT system, x, y, z FROM system_seen WHERE x IS NOT NULL
    UNION ALL
    SELECT ?::VARCHAR, x, y, z FROM target
),
reach AS (
    SELECT c.system,
           sqrt(pow(c.x - k.cx, 2) + pow(c.y - k.cy, 2) + pow(c.z - k.cz, 2)) AS jump_ly,
           sqrt(pow(c.x - t.x, 2) + pow(c.y - t.y, 2) + pow(c.z - t.z, 2)) AS left_ly
    FROM candidates c, carrier k, target t
    WHERE c.x IS NOT NULL
),
best AS (
    SELECT system, jump_ly, left_ly FROM reach
    WHERE jump_ly <= {{CARRIER_RANGE_LY}} AND jump_ly > {{CARRIER_SAME_LY}}
    ORDER BY left_ly, jump_ly DESC, system
    LIMIT 1
)
SELECT t.x, t.y, t.z, b.system, b.jump_ly, b.left_ly
FROM target t
LEFT JOIN best b ON true

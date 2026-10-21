SELECT 'system_seen' AS t, count(*) AS n FROM system_seen
UNION ALL SELECT 'system_visited', count(*) FROM system_visited
UNION ALL SELECT 'system_confirmed', count(*) FROM system_confirmed
UNION ALL SELECT 'poi_visited', count(*) FROM poi_visited

SELECT s.market_id, s.name, s.system_name, s.system_id64
FROM staging.spansh_station_service s
WHERE NOT EXISTS (SELECT 1 FROM main.system_known k WHERE k.system_id = s.system_id64)
ORDER BY s.name;

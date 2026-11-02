SELECT t.market_id, t.station, coalesce(t.material_trader, '-'), coalesce(t.technology_broker, '-')
FROM main.station_service t
WHERE t.is_listed
  AND NOT EXISTS (SELECT 1 FROM transform.station_service s WHERE s.market_id = t.market_id)
ORDER BY t.station;

SELECT
  (SELECT count(*) FROM transform.station_service s
   WHERE NOT EXISTS (SELECT 1 FROM main.station_service t WHERE t.market_id = s.market_id)),
  (SELECT count(*) FROM main.station_service t JOIN transform.station_service s USING (market_id)
   WHERE t.system_id IS DISTINCT FROM s.system_id
      OR t.station IS DISTINCT FROM s.station
      OR t.station_type IS DISTINCT FROM s.station_type
      OR t.distance_to_arrival_ls IS DISTINCT FROM s.distance_to_arrival_ls
      OR t.is_planetary IS DISTINCT FROM s.is_planetary
      OR t.has_large_pad IS DISTINCT FROM s.has_large_pad
      OR t.material_trader IS DISTINCT FROM s.material_trader
      OR t.technology_broker IS DISTINCT FROM s.technology_broker
      OR t.has_universal_cartographics IS DISTINCT FROM s.has_universal_cartographics
      OR t.last_reported IS DISTINCT FROM s.last_reported
      OR t.x IS DISTINCT FROM s.x OR t.y IS DISTINCT FROM s.y OR t.z IS DISTINCT FROM s.z
      OR NOT t.is_listed)
  + (SELECT count(*) FROM main.station_service t
     WHERE t.is_listed
       AND NOT EXISTS (SELECT 1 FROM transform.station_service s WHERE s.market_id = t.market_id));

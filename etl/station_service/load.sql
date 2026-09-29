MERGE INTO main.station_service AS t
USING transform.station_service AS s ON t.market_id = s.market_id
WHEN MATCHED AND (
      t.system_id IS DISTINCT FROM s.system_id
      OR t.system IS DISTINCT FROM s.system
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
    THEN UPDATE SET system_id = s.system_id, system = s.system, station = s.station,
                    station_type = s.station_type,
                    distance_to_arrival_ls = s.distance_to_arrival_ls,
                    is_planetary = s.is_planetary, has_large_pad = s.has_large_pad,
                    material_trader = s.material_trader,
                    technology_broker = s.technology_broker,
                    has_universal_cartographics = s.has_universal_cartographics,
                    last_reported = s.last_reported, is_listed = true,
                    x = s.x, y = s.y, z = s.z
WHEN NOT MATCHED
    THEN INSERT (market_id, system_id, system, station, station_type, distance_to_arrival_ls,
                 is_planetary, has_large_pad, material_trader, technology_broker,
                 has_universal_cartographics, last_reported, is_listed, x, y, z)
         VALUES (s.market_id, s.system_id, s.system, s.station, s.station_type,
                 s.distance_to_arrival_ls, s.is_planetary, s.has_large_pad,
                 s.material_trader, s.technology_broker, s.has_universal_cartographics,
                 s.last_reported, true, s.x, s.y, s.z)
WHEN NOT MATCHED BY SOURCE AND t.is_listed
    THEN UPDATE SET is_listed = false;

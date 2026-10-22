MERGE INTO main.station AS t
USING transform.station AS s ON t.market_id = s.market_id
WHEN MATCHED AND (t.system_id IS DISTINCT FROM s.system_id
      OR t.system IS DISTINCT FROM s.system
      OR t.station IS DISTINCT FROM s.station
      OR t.station_type IS DISTINCT FROM s.station_type
      OR t.is_carrier IS DISTINCT FROM s.is_carrier
      OR t.distance_to_arrival_ls IS DISTINCT FROM s.distance_to_arrival_ls
      OR t.large_pads IS DISTINCT FROM s.large_pads
      OR t.has_universal_cartographics IS DISTINCT FROM s.has_universal_cartographics
      OR t.has_vista_genomics IS DISTINCT FROM s.has_vista_genomics
      OR t.has_repair IS DISTINCT FROM s.has_repair
      OR t.has_restock IS DISTINCT FROM s.has_restock
      OR t.has_refuel IS DISTINCT FROM s.has_refuel
      OR t.last_reported IS DISTINCT FROM s.last_reported
      OR t.x IS DISTINCT FROM s.x
      OR t.y IS DISTINCT FROM s.y
      OR t.z IS DISTINCT FROM s.z
      OR NOT t.is_listed)
    THEN UPDATE SET system_id = s.system_id,
                    system = s.system,
                    station = s.station,
                    station_type = s.station_type,
                    is_carrier = s.is_carrier,
                    distance_to_arrival_ls = s.distance_to_arrival_ls,
                    large_pads = s.large_pads,
                    has_universal_cartographics = s.has_universal_cartographics,
                    has_vista_genomics = s.has_vista_genomics,
                    has_repair = s.has_repair,
                    has_restock = s.has_restock,
                    has_refuel = s.has_refuel,
                    last_reported = s.last_reported,
                    x = s.x,
                    y = s.y,
                    z = s.z,
                    is_listed = true
WHEN NOT MATCHED
    THEN INSERT (market_id, system_id, system, station, station_type, is_carrier, distance_to_arrival_ls, large_pads, has_universal_cartographics, has_vista_genomics, has_repair, has_restock, has_refuel, last_reported, x, y, z, is_listed)
         VALUES (s.market_id, s.system_id, s.system, s.station, s.station_type, s.is_carrier, s.distance_to_arrival_ls, s.large_pads, s.has_universal_cartographics, s.has_vista_genomics, s.has_repair, s.has_restock, s.has_refuel, s.last_reported, s.x, s.y, s.z, true)
WHEN NOT MATCHED BY SOURCE AND t.is_listed
    THEN UPDATE SET is_listed = false;

SELECT
  (SELECT count(*) FROM transform.station s
   WHERE NOT EXISTS (SELECT 1 FROM main.station t WHERE t.market_id = s.market_id)),
  (SELECT count(*) FROM main.station t JOIN transform.station s ON t.market_id = s.market_id
   WHERE t.system_id IS DISTINCT FROM s.system_id
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
  + (SELECT count(*) FROM main.station t
     WHERE t.is_listed AND NOT EXISTS (SELECT 1 FROM transform.station s WHERE s.market_id = t.market_id));

SELECT
  (SELECT count(*) FROM transform.carrier s
   WHERE NOT EXISTS (SELECT 1 FROM main.carrier t WHERE t.callsign = s.callsign)),
  (SELECT count(*) FROM main.carrier t JOIN transform.carrier s USING (callsign)
   WHERE t.carrier_name IS DISTINCT FROM s.carrier_name
      OR t.last_moved   IS DISTINCT FROM s.last_moved
      OR t.last_seen    IS DISTINCT FROM s.last_seen
      OR t.has_universal_cartographics IS DISTINCT FROM s.has_universal_cartographics
      OR t.is_reliable  IS DISTINCT FROM s.is_reliable
      OR t.system_id    IS DISTINCT FROM s.system_id);

SELECT
  (SELECT count(*) FROM transform.carrier_position s
   WHERE NOT EXISTS (SELECT 1 FROM main.carrier_position t
                     WHERE t.callsign = s.callsign)),
  (SELECT count(*) FROM main.carrier_position t
   JOIN transform.carrier_position s USING (callsign)
   WHERE t.system IS DISTINCT FROM s.system
      OR t.x      IS DISTINCT FROM s.x
      OR t.y      IS DISTINCT FROM s.y
      OR t.z      IS DISTINCT FROM s.z);

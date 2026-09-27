SELECT t.callsign, coalesce(t.carrier_name, '(unnamed)')
FROM main.carrier t
WHERE NOT EXISTS (SELECT 1 FROM transform.carrier s WHERE s.callsign = t.callsign)
ORDER BY t.callsign;

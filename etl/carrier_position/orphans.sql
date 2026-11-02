SELECT t.callsign, t.system
FROM main.carrier_position t
WHERE NOT EXISTS (SELECT 1 FROM transform.carrier_position s
                  WHERE s.callsign = t.callsign)
ORDER BY t.callsign;

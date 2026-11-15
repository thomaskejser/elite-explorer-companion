SELECT c.callsign, p.x, p.y, p.z
FROM {{MODEL}}.carrier c
JOIN {{MODEL}}.carrier_position p USING (callsign)
WHERE c.is_reliable

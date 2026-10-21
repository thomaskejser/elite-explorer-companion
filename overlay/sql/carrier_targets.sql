WITH near AS (
  SELECT c.callsign, c.carrier_name, cp.system,
         cp.x, cp.y, cp.z,
         CASE WHEN cp.x IS NULL THEN NULL
              ELSE sqrt(pow(cp.x - ?, 2) + pow(cp.y - ?, 2) + pow(cp.z - ?, 2)) END AS dist_ly,
         c.has_universal_cartographics AS uc
  FROM {{MODEL}}.carrier c
  JOIN {{MODEL}}.carrier_position cp ON cp.callsign = c.callsign
  WHERE c.is_reliable
)
SELECT row_number() OVER (ORDER BY dist_ly) AS rank,
       system,
       'CARRIER' AS type_label,
       dist_ly, FALSE AS dist_approx,
       {{P_NULLS}},
       {{ROW_CARRIER}} AS row_grp,
       CASE WHEN uc THEN '+UC ' ELSE '' END || coalesce(carrier_name, '(unnamed)') AS wide_text,
       callsign AS detail,
       NULL::VARCHAR AS mass_code, NULL::VARCHAR AS boxel,
       x, y, z,
       NULL::DOUBLE AS dist_sol, NULL::VARCHAR AS star_class
FROM near ORDER BY dist_ly LIMIT ?

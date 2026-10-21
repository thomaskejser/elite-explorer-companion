WITH ranked AS (
  SELECT s.system, s.station, s.material_trader, s.distance_to_arrival_ls,
         s.x, s.y, s.z,
         CASE WHEN s.x IS NULL THEN NULL
              ELSE sqrt(pow(s.x - ?, 2) + pow(s.y - ?, 2) + pow(s.z - ?, 2)) END AS dist_ly
  FROM {{MODEL}}.station_service s
  WHERE s.is_listed AND s.material_trader IS NOT NULL AND s.x IS NOT NULL
),
kept AS (
  SELECT *, row_number() OVER (PARTITION BY material_trader ORDER BY dist_ly, station) AS rn
  FROM ranked
)
SELECT row_number() OVER (ORDER BY CASE material_trader
                                     WHEN 'Raw' THEN 1
                                     WHEN 'Manufactured' THEN 2
                                     ELSE 3 END, rn) AS rank,
       system,
       CASE material_trader WHEN 'Raw' THEN 'RAW'
                            WHEN 'Manufactured' THEN 'MANUF'
                            ELSE 'ENCODED' END AS type_label,
       dist_ly, FALSE AS dist_approx,
       {{P_NULLS}},
       {{ROW_TRADER}} AS row_grp,
       station || coalesce(' ' || CAST(round(distance_to_arrival_ls) AS BIGINT) || ' ls', '')
         AS wide_text,
       station AS detail,
       NULL::VARCHAR AS mass_code, NULL::VARCHAR AS boxel,
       x, y, z,
       NULL::DOUBLE AS dist_sol, NULL::VARCHAR AS star_class
FROM kept WHERE rn <= ? ORDER BY rank

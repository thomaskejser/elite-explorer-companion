WITH {{CONFIRMED_CTE}},
scored AS (
  SELECT *,
         CASE WHEN x IS NULL THEN NULL
              ELSE sqrt(pow(x - ?, 2) + pow(y - ?, 2) + pow(z - ?, 2)) END AS dist_ly
  FROM confirmed
),
ranked AS (
  SELECT *,
         row_number() OVER (PARTITION BY kind ORDER BY dist_ly IS NULL, dist_ly, system) AS rn,
         count(*) OVER (PARTITION BY kind) AS kind_count
  FROM scored
)
SELECT system,
       CASE {{ABBR_CASE}} END AS type_label,
       dist_ly, FALSE AS dist_approx,
       kind_count,
       {{ROW_CONFIRMED}} AS row_grp, NULL::VARCHAR AS wide_text,
       star_class AS detail,
       NULL::VARCHAR AS mass_code, NULL::VARCHAR AS boxel,
       x, y, z,
       NULL::DOUBLE AS dist_sol, star_class
FROM ranked
WHERE rn = 1
ORDER BY CASE {{RANK_CASE}} ELSE 99 END

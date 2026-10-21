SELECT row_number() OVER (ORDER BY u.band, u.nearest_ly NULLS LAST, u.system) AS rank,
       u.system,
       'UNFOUND' AS type_label,
       CASE WHEN u.x IS NULL THEN NULL
            ELSE sqrt(pow(u.x - ?, 2) + pow(u.y - ?, 2) + pow(u.z - ?, 2)) END AS dist_ly,
       u.band <> 'near' AS dist_approx,
       {{P_NULLS}},
       {{ROW_UNFOUND}} AS row_grp,
       printf('%-4s %-9s  %s',
              upper(u.band), coalesce(u.sp_type, ''),
              CASE WHEN u.nearest IS NULL
                   THEN 'no hand-named system within 20 ly'
                   ELSE printf('fly to %s  (%.2f ly)', u.nearest, u.nearest_ly)
              END) AS wide_text,
       u.nearest AS detail,
       NULL::VARCHAR AS mass_code, NULL::VARCHAR AS boxel,
       u.x, u.y, u.z, u.dist_ly AS dist_sol,
       NULL::VARCHAR AS star_class
FROM {{MODEL}}.system_unfound u
WHERE u.sector = ?
  AND u.system NOT IN (SELECT system FROM system_visited)
  AND u.system NOT IN (SELECT system FROM system_wrong)
ORDER BY rank LIMIT ?

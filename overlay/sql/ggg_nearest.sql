WITH known AS (
  SELECT system, min(detail) AS detail, max(x) AS x, max(y) AS y, max(z) AS z
  FROM (
    SELECT cs.system, cs.entry AS detail, cs.x, cs.y, cs.z
    FROM {{MODEL}}.codex_sighting cs
    WHERE cs.category = 'Planets' AND cs.codex LIKE 'codex_ent_green_%'
    UNION ALL
    SELECT sp.system, p.poi AS detail, sp.x, sp.y, sp.z
    FROM {{MODEL}}.system_poi sp
    JOIN {{MODEL}}.poi p USING (poi_id)
    WHERE p.poi_class = 'ggg'
  )
  WHERE x IS NOT NULL
    AND system NOT IN (SELECT system FROM system_visited)
  GROUP BY system
),
predicted AS (
  SELECT g.system, min(g.body) AS detail, max(g.x) AS x, max(g.y) AS y, max(g.z) AS z
  FROM {{MODEL}}.system_green_giant g
  WHERE g.x IS NOT NULL
    AND g.system NOT IN (SELECT system FROM system_visited)
    AND g.system NOT IN (SELECT system FROM known)
  GROUP BY g.system
),
found AS (
  SELECT 'GGG' AS type_label, * FROM known
  UNION ALL
  SELECT '~GGG' AS type_label, * FROM predicted
),
ranked AS (
  SELECT *,
         sqrt(pow(x - ?, 2) + pow(y - ?, 2) + pow(z - ?, 2)) AS dist_ly,
         row_number() OVER (PARTITION BY type_label ORDER BY sqrt(pow(x - ?, 2) + pow(y - ?, 2) + pow(z - ?, 2)), system) AS rn
  FROM found
)
SELECT row_number() OVER (ORDER BY dist_ly, system) AS rank,
       system,
       type_label,
       dist_ly, FALSE AS dist_approx,
       {{P_NULLS}},
       {{ROW_GGG}} AS row_grp,
       NULL::VARCHAR AS wide_text,
       detail, NULL::VARCHAR AS mass_code,
       NULL::VARCHAR AS boxel,
       x, y, z,
       NULL::DOUBLE AS dist_sol, NULL::VARCHAR AS star_class
FROM ranked
WHERE rn = 1
ORDER BY dist_ly, system

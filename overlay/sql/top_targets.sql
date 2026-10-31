WITH {{CONFIRMED_CTE}},
sys AS (
  SELECT p.*, {{SEEN_CLASS}} AS star_class,
         CASE WHEN p.is_catalog THEN {{ROW_CATALOG}} ELSE {{ROW_PREDICTED}} END AS row_grp
  FROM {{MODEL}}.system_predicted p
  {{SEEN_JOIN}}
  WHERE p.sector = ? AND {{OFFERABLE}}
    AND p.system NOT IN (SELECT system FROM confirmed)
    AND (p.mass_code = 'h' OR greatest({{RARE_MAX}}) >= {{MIN_RARE}})
),
poi_raw AS (
  SELECT sp.system, po.poi, po.poi_class, sp.x, sp.y, sp.z
  FROM {{MODEL}}.system_poi sp
  JOIN {{MODEL}}.poi po ON po.poi_id = sp.poi_id
  WHERE sp.sector = ?
),
poi AS (
  SELECT system, min(poi) AS poi, min(poi_class) AS poi_class,
         max(x) AS x, max(y) AS y, max(z) AS z,
         row_number() OVER (ORDER BY sqrt(pow(max(x) - ?, 2) + pow(max(y) - ?, 2)
                                          + pow(max(z) - ?, 2)) NULLS LAST,
                                     min(poi_class), system) AS pr
  FROM poi_raw
  WHERE system NOT IN (SELECT system FROM poi_visited)
    AND system NOT IN (SELECT system FROM system_visited)
    AND system NOT IN (SELECT system FROM confirmed)
  GROUP BY system
),
unioned AS (
  SELECT {{ROW_POI}} AS row_grp, pr AS ord, system,
         upper(poi_class) AS type_label, poi AS detail,
         {{P_NULLS}},
         NULL::VARCHAR AS mass_code, NULL::VARCHAR AS boxel,
         x, y, z,
         FALSE AS dist_approx,
         NULL::DOUBLE AS dist_sol, NULL::VARCHAR AS star_class
  FROM poi WHERE pr <= {{MAX_POI_ROWS}}
  UNION ALL
  SELECT row_grp,
         row_number() OVER (PARTITION BY row_grp
                            ORDER BY mass_code DESC NULLS LAST, {{RANK_BY_BARE}} DESC, exp_bodies DESC, system),
         system,
         CASE WHEN mass_code IS NULL THEN '?' ELSE 'Mass ' || upper(mass_code) END,
         NULL,
         {{P_COLUMNS}},
         mass_code, boxel, x, y, z,
         NOT is_catalog AS dist_approx,
         dist_sol, star_class
  FROM sys
),
ranked AS (
  SELECT *,
         CASE WHEN x IS NULL THEN NULL
              ELSE sqrt(pow(x - ?, 2) + pow(y - ?, 2) + pow(z - ?, 2)) END AS dist_ly,
         row_number() OVER (ORDER BY row_grp, ord) AS rank
  FROM unioned
)
SELECT rank,
       system,
       type_label,
       {{P_COLUMNS}},
       dist_ly, dist_approx,
       NULL::VARCHAR AS wide_text,
       row_grp, detail, mass_code, boxel, x, y, z, dist_sol, star_class
FROM ranked ORDER BY rank LIMIT ?

WITH pool AS (
  SELECT p.sector, p.system, p.exp_bodies,
         {{P_COLUMNS_P}},
         {{RANK_BY}} AS rank_score,
         {{SEEN_CLASS}} AS star_class
  FROM {{MODEL}}.system_predicted p
  LEFT JOIN system_visited v ON v.system = p.system
  {{SEEN_JOIN}}
  WHERE NOT p.is_catalog AND v.system IS NULL
    AND p.sector IS NOT NULL
    AND {{SEEN_CLASS}} IS NULL
    AND p.sector IS DISTINCT FROM ?
),
agg AS (SELECT sector, count(*) AS n, {{P_SUMS_BARE}} FROM pool GROUP BY sector),
best AS (
  SELECT sector, list(system ORDER BY rn) AS candidates FROM (
    SELECT p.sector, p.system,
           row_number() OVER (
             PARTITION BY p.sector
             ORDER BY p.rank_score DESC, p.exp_bodies DESC, p.system) AS rn
    FROM pool p
    WHERE greatest({{RARE_MAX}}) >= {{MIN_RARE}}
      AND p.system NOT IN (SELECT system FROM system_wrong)
  ) WHERE rn <= {{SECTOR_CANDIDATES}}
  GROUP BY sector
),
near AS (
  SELECT a.*, b.candidates[1] AS best_system, b.candidates,
         CASE WHEN k.x IS NULL THEN NULL
              ELSE sqrt(pow(k.x - ?, 2) + pow(k.y - ?, 2) + pow(k.z - ?, 2)) END AS dist_ly
  FROM agg a
  JOIN {{MODEL}}.sector k ON k.sector = a.sector
  JOIN best b ON b.sector = a.sector
  ORDER BY dist_ly LIMIT ?
)
SELECT row_number() OVER (ORDER BY dist_ly) AS rank,
       n.sector AS system,
       'Σ ' || format('{:,}', n.n) AS type_label,
       n.dist_ly,
       TRUE AS dist_approx,
       {{P_COLUMNS_N}},
       {{ROW_SECTOR}} AS row_grp, NULL::VARCHAR AS wide_text,
       n.best_system AS detail, n.best_system AS copy_text,
       n.candidates AS candidates,
       NULL::VARCHAR AS mass_code, NULL::VARCHAR AS boxel,
       NULL::DOUBLE AS x, NULL::DOUBLE AS y, NULL::DOUBLE AS z,
       NULL::DOUBLE AS dist_sol, NULL::VARCHAR AS star_class
FROM near n
ORDER BY rank

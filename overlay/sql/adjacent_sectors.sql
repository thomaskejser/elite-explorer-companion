WITH ship AS (
  SELECT ?::DOUBLE AS px, ?::DOUBLE AS py, ?::DOUBLE AS pz
),
here AS (
  SELECT floor((px + 49985) / 1280)::BIGINT AS cx,
         floor((py + 40985) / 1280)::BIGINT AS cy,
         floor((pz + 24105) / 1280)::BIGINT AS cz
  FROM ship
),
cube AS (
  SELECT a.dx, b.dy, c.dz,
         h.cx + a.dx + 128 * (h.cy + b.dy) + 16384 * (h.cz + c.dz) AS sector_id
  FROM here h, range(-1, 2) a(dx), range(-1, 2) b(dy), range(-1, 2) c(dz)
),
named AS (
  SELECT c.*, k.sector
  FROM cube c
  LEFT JOIN {{MODEL}}.sector k ON k.sector_id = c.sector_id
),
pool AS (
  SELECT p.sector, p.system, p.exp_bodies, p.mass_code,
         sqrt(pow(p.x - s.px, 2) + pow(p.y - s.py, 2) + pow(p.z - s.pz, 2)) AS ship_ly,
         {{P_COLUMNS_P}},
         {{RANK_BY}} AS rank_score
  FROM {{MODEL}}.system_predicted p
  CROSS JOIN ship s
  {{SEEN_JOIN}}
  WHERE NOT p.is_catalog
    AND p.sector IN (SELECT sector FROM named WHERE sector IS NOT NULL)
    AND {{OFFERABLE}}
),
agg AS (
  SELECT sector,
         count(*) FILTER (WHERE mass_code = 'h') AS n_h,
         count(*) FILTER (WHERE mass_code = 'g') AS n_g,
         count(*) FILTER (WHERE mass_code = 'f') AS n_f,
         count(*) FILTER (WHERE mass_code = 'e') AS n_e,
         {{P_SUMS_BARE}}
  FROM pool GROUP BY sector
),
best AS (
  SELECT sector, list(system ORDER BY rn) AS candidates, min_by(ship_ly, rn) AS first_ly FROM (
    SELECT p.sector, p.system, p.ship_ly,
           row_number() OVER (
             PARTITION BY p.sector
             ORDER BY p.mass_code DESC NULLS LAST, p.rank_score DESC, p.exp_bodies DESC, p.system) AS rn
    FROM pool p
    WHERE p.mass_code = 'h' OR greatest({{RARE_MAX}}) >= {{MIN_RARE}}
  ) WHERE rn <= {{SECTOR_CANDIDATES}}
  GROUP BY sector
),
n AS (
  SELECT c.dx, c.dy, c.dz, c.sector, a.n_h, a.n_g, a.n_f, a.n_e, {{P_COLUMNS_A}}, b.candidates, b.first_ly
  FROM named c
  LEFT JOIN agg a ON a.sector = c.sector
  LEFT JOIN best b ON b.sector = c.sector
)
SELECT row_number() OVER (ORDER BY n.dy DESC,
                                   CASE 3 * n.dz + n.dx
                                     WHEN 0 THEN 0 WHEN 3 THEN 1 WHEN 4 THEN 2 WHEN 1 THEN 3 WHEN -2 THEN 4
                                     WHEN -3 THEN 5 WHEN -4 THEN 6 WHEN -1 THEN 7 WHEN 2 THEN 8 END) AS rank,
       coalesce(n.sector, '{{UNNAMED_SECTOR}}') AS system,
       n.n_h, n.n_g, n.n_f, n.n_e,
       n.first_ly AS dist_ly,
       TRUE AS dist_approx,
       {{P_COLUMNS_N}},
       CASE WHEN n.sector IS NULL THEN {{ROW_SECTOR_UNNAMED}} ELSE {{ROW_SECTOR}} END AS row_grp,
       NULL::VARCHAR AS wide_text,
       n.candidates[1] AS detail, n.candidates[1] AS copy_text,
       n.candidates AS candidates,
       n.dx, n.dy, n.dz,
       NULL::VARCHAR AS mass_code, NULL::VARCHAR AS boxel,
       NULL::DOUBLE AS x, NULL::DOUBLE AS y, NULL::DOUBLE AS z,
       NULL::DOUBLE AS dist_sol, NULL::VARCHAR AS star_class
FROM n
ORDER BY rank

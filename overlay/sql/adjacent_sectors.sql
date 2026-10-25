WITH ship AS (
  SELECT ?::DOUBLE AS px, ?::DOUBLE AS py, ?::DOUBLE AS pz
),
here AS (
  SELECT px, py, pz,
         floor((px + 49985) / 1280)::BIGINT AS cx,
         floor((py + 40985) / 1280)::BIGINT AS cy,
         floor((pz + 24105) / 1280)::BIGINT AS cz
  FROM ship
),
cube AS (
  SELECT a.dx, b.dy, c.dz,
         h.cx + a.dx + 128 * (h.cy + b.dy) + 16384 * (h.cz + c.dz) AS sector_id,
         sqrt(pow(greatest(-49985 + (h.cx + a.dx) * 1280 - h.px, 0,
                           h.px + 49985 - (h.cx + a.dx + 1) * 1280), 2)
              + pow(greatest(-40985 + (h.cy + b.dy) * 1280 - h.py, 0,
                             h.py + 40985 - (h.cy + b.dy + 1) * 1280), 2)
              + pow(greatest(-24105 + (h.cz + c.dz) * 1280 - h.pz, 0,
                             h.pz + 24105 - (h.cz + c.dz + 1) * 1280), 2)) AS dist_ly
  FROM here h, range(-1, 2) a(dx), range(-1, 2) b(dy), range(-1, 2) c(dz)
  WHERE NOT (a.dx = 0 AND b.dy = 0 AND c.dz = 0)
),
named AS (
  SELECT c.*, k.sector
  FROM cube c
  LEFT JOIN {{MODEL}}.sector k ON k.sector_id = c.sector_id
),
pool AS (
  SELECT p.sector, p.system, p.exp_bodies,
         {{P_COLUMNS_P}},
         {{RANK_BY}} AS rank_score
  FROM {{MODEL}}.system_predicted p
  {{SEEN_JOIN}}
  WHERE NOT p.is_catalog
    AND p.sector IN (SELECT sector FROM named WHERE sector IS NOT NULL)
    AND {{OFFERABLE}}
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
  ) WHERE rn <= {{SECTOR_CANDIDATES}}
  GROUP BY sector
),
n AS (
  SELECT c.dx, c.dy, c.dz, c.dist_ly, c.sector, a.n, {{P_COLUMNS_A}}, b.candidates
  FROM named c
  LEFT JOIN agg a ON a.sector = c.sector
  LEFT JOIN best b ON b.sector = c.sector
)
SELECT row_number() OVER (ORDER BY CASE n.dy WHEN 0 THEN 0 WHEN -1 THEN 1 ELSE 2 END,
                                   n.dist_ly, n.dz DESC, n.dx) AS rank,
       coalesce(n.sector, '{{UNNAMED_SECTOR}}') AS system,
       CASE WHEN n.n IS NULL THEN NULL ELSE 'Σ ' || format('{:,}', n.n) END AS type_label,
       n.dist_ly,
       FALSE AS dist_approx,
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

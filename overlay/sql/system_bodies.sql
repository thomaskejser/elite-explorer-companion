WITH b AS (
  SELECT unnest(from_json(?, '[{"body":"VARCHAR","cls":"VARCHAR","atmo":"VARCHAR","temp":"DOUBLE","ls":"DOUBLE","landable":"BOOLEAN","volcanism":"VARCHAR","known":"BOOLEAN","bio":"INTEGER","geo":"INTEGER","genera":["VARCHAR"],"logged":"INTEGER","logged_genera":["VARCHAR"],"footfalled":"BOOLEAN"}]'), recursive := true)
),
keyed AS (
  SELECT b.*,
         CASE cls WHEN 'High metal content body' THEN 'High metal content world'
                  WHEN 'Rocky ice body' THEN 'Rocky Ice world'
                  WHEN 'Metal rich body' THEN 'Metal-rich body'
                  WHEN 'Earthlike body' THEN 'Earth-like world'
                  ELSE cls END AS body_type,
         CAST(least(greatest(floor(temp / 20) * 20, 100), 440) AS INTEGER) AS temp_band,
         bio = 0 AND NOT coalesce(known, false) AND landable IS NOT FALSE AS unknown_bio,
         CASE WHEN footfalled = false AND landable IS NOT FALSE THEN {{FIRST_FOOTFALL_BONUS}} ELSE 1 END AS bonus
  FROM b
),
odds AS (
  SELECT k.body, o.star, o.bodies, o.p_bio, o.signals_bio, o.codexed_bodies, o.cr_species
  FROM keyed k
  JOIN {{MODEL}}.exobio_odds o
    ON lower(replace(replace(o.atmosphere, '-', ' '), 'Sulphur', 'Sulfur')) || ' atmosphere' = lower(k.atmo)
   AND o.body_type = k.body_type AND o.temp_band = k.temp_band
   AND o.star IN (?, '*')
),
cell AS (
  SELECT body,
         coalesce(max(p_bio) FILTER (WHERE star <> '*' AND bodies >= {{EXOBIO_MIN_BODIES}}),
                  max(p_bio) FILTER (WHERE star = '*')) AS p_bio,
         coalesce(max(signals_bio) FILTER (WHERE star <> '*' AND bodies >= {{EXOBIO_MIN_BODIES}}),
                  max(signals_bio) FILTER (WHERE star = '*')) AS signals_bio,
         coalesce(max(cr_species) FILTER (WHERE star <> '*' AND codexed_bodies >= {{EXOBIO_MIN_CODEXED}}),
                  max(cr_species) FILTER (WHERE star = '*')) AS cr_species
  FROM odds
  GROUP BY body
),
gshare AS (
  SELECT k.body, g.genus, g.share, g.cr_genus
  FROM keyed k
  JOIN odds o ON o.body = k.body
  JOIN {{MODEL}}.exobio_genus_odds g
    ON lower(replace(replace(g.atmosphere, '-', ' '), 'Sulphur', 'Sulfur')) || ' atmosphere' = lower(k.atmo)
   AND g.body_type = k.body_type AND g.temp_band = k.temp_band AND g.star = o.star
  WHERE (o.star <> '*') = EXISTS (SELECT 1 FROM odds x
                                  WHERE x.body = k.body AND x.star <> '*'
                                    AND x.codexed_bodies >= {{EXOBIO_MIN_CODEXED}})
),
gname AS (
  SELECT genus, min(genus_key) AS genus_key, round(avg(cr_value)) AS cr
  FROM {{MODEL}}.exobio_species
  GROUP BY genus
),
named_genus AS (
  SELECT k.body, n.genus
  FROM (SELECT body, unnest(genera) AS name FROM keyed) k
  JOIN gname n ON k.name IN (n.genus, n.genus_key)
),
done_genus AS (
  SELECT k.body, n.genus
  FROM (SELECT body, unnest(logged_genera) AS name FROM keyed) k
  JOIN gname n ON k.name IN (n.genus, n.genus_key)
),
picks AS (
  SELECT c.body, c.genus, NULL::DOUBLE AS chance, coalesce(s.cr_genus, n.cr) * k.bonus AS cr
  FROM named_genus c
  JOIN keyed k USING (body)
  JOIN gname n USING (genus)
  LEFT JOIN gshare s USING (body, genus)
  UNION ALL
  SELECT s.body, s.genus, CASE WHEN k.bio > 0 THEN s.share ELSE c.p_bio * s.share END, s.cr_genus * k.bonus
  FROM gshare s
  JOIN keyed k USING (body)
  LEFT JOIN cell c USING (body)
  WHERE NOT EXISTS (SELECT 1 FROM named_genus n WHERE n.body = s.body)
    AND (k.bio > k.logged OR k.unknown_bio)
),
remaining AS (
  SELECT *
  FROM picks p
  WHERE NOT EXISTS (SELECT 1 FROM done_genus d WHERE d.body = p.body AND d.genus = p.genus)
    AND (chance IS NULL OR chance >= {{GENUS_MIN_CHANCE}})
  QUALIFY chance IS NULL
       OR row_number() OVER (PARTITION BY body ORDER BY chance DESC, genus) <= {{GENUS_ROWS}}
),
genera AS (
  SELECT body,
         string_agg(genus || '|' || coalesce(CAST(round(chance, 3) AS VARCHAR), '') || '|' || coalesce(CAST(CAST(cr AS BIGINT) AS VARCHAR), ''),
                    ';' ORDER BY chance DESC NULLS FIRST, cr DESC, genus) AS genera,
         sum(cr) FILTER (WHERE chance IS NULL) AS confirmed_cr,
         count(*) AS shown
  FROM remaining
  GROUP BY body
),
logged AS (
  SELECT unnest(from_json(?, '["VARCHAR"]')) AS codex
),
geology AS (
  SELECT DISTINCT codex FROM {{MODEL}}.codex_sighting WHERE category = 'Geology'
),
erupting AS (
  SELECT body, body_type,
         replace(replace(replace(regexp_replace(lower(volcanism), '^(major|minor) | volcanism$', '', 'g'),
                                 'metallic magma', 'iron magma'), 'rocky magma', 'silicate magma'), ' ', '') AS material
  FROM keyed
  WHERE geo > 0 AND volcanism IS NOT NULL
),
unlogged AS (
  SELECT e.body, bool_or(l.codex IS NULL) AS geo_new
  FROM erupting e
  JOIN geology g ON ends_with(g.codex, '_' || e.material)
                AND starts_with(g.codex, 'codex_ent_ice') = (e.body_type IN ('Icy body', 'Rocky Ice world'))
  LEFT JOIN logged l ON l.codex = g.codex
  GROUP BY e.body
),
valued AS (
  SELECT k.body, k.body_type, k.ls, k.bio, k.logged, k.geo,
         k.bonus > 1 AS first_footfall,
         CASE WHEN k.unknown_bio THEN c.p_bio END AS chance,
         CASE WHEN g.confirmed_cr IS NOT NULL THEN g.confirmed_cr
              WHEN k.bio > 0 THEN greatest(k.bio - k.logged, 0) * c.cr_species * k.bonus
              WHEN k.unknown_bio THEN c.p_bio * c.signals_bio * c.cr_species * k.bonus END AS cr,
         g.genera,
         u.geo_new,
         k.bio > k.logged AND NOT EXISTS (SELECT 1 FROM named_genus n WHERE n.body = k.body) AS bio_left,
         coalesce(g.shown, 0) > 0 AS genera_left
  FROM keyed k
  LEFT JOIN cell c USING (body)
  LEFT JOIN genera g USING (body)
  LEFT JOIN unlogged u USING (body)
),
worth AS (
  SELECT *
  FROM valued
  WHERE genera_left OR bio_left OR (chance > 0 AND cr > 0) OR (geo > 0 AND geo_new)
)
SELECT body,
       CASE body_type WHEN 'Earth-like world' THEN 'Earth-like'
                      WHEN 'High metal content world' THEN 'HMC'
                      WHEN 'Rocky Ice world' THEN 'Rocky ice'
                      WHEN 'Rocky body' THEN 'Rocky'
                      WHEN 'Icy body' THEN 'Icy'
                      WHEN 'Metal-rich body' THEN 'Metal-rich'
                      ELSE coalesce(body_type, '') END AS kind,
       ls, bio, logged, geo, first_footfall, chance, round(cr) AS cr, genera, geo_new
FROM worth
ORDER BY CASE WHEN genera_left OR bio_left THEN 0 WHEN chance > 0 THEN 1 ELSE 2 END,
         cr DESC NULLS LAST, geo DESC, ls NULLS LAST, body
LIMIT {{SYSTEM_BODY_ROWS}};

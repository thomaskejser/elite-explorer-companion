WITH b AS (
  SELECT unnest(from_json(?, '[{"body":"VARCHAR","cls":"VARCHAR","atmo":"VARCHAR","temp":"DOUBLE","bio":"INTEGER","logged":"INTEGER","footfalled":"BOOLEAN"}]'), recursive := true)
),
keyed AS (
  SELECT b.*,
         CASE cls WHEN 'High metal content body' THEN 'High metal content world'
                  WHEN 'Rocky ice body' THEN 'Rocky Ice world'
                  WHEN 'Metal rich body' THEN 'Metal-rich body'
                  ELSE cls END AS body_type,
         CAST(least(greatest(floor(temp / 20) * 20, 100), 440) AS INTEGER) AS temp_band
  FROM b
),
odds AS (
  SELECT k.body,
         o.star, o.codexed_bodies, o.cr_species, o.likely_species
  FROM keyed k
  JOIN {{MODEL}}.exobio_odds o
    ON lower(replace(replace(o.atmosphere, '-', ' '), 'Sulphur', 'Sulfur')) || ' atmosphere' = lower(k.atmo)
   AND o.body_type = k.body_type AND o.temp_band = k.temp_band
   AND o.star IN (?, '*')
),
best AS (
  SELECT * FROM odds
  QUALIFY row_number() OVER (PARTITION BY body
                             ORDER BY (star <> '*' AND codexed_bodies >= {{EXOBIO_MIN_CODEXED}}) DESC) = 1
)
SELECT k.body, k.bio, k.logged, k.footfalled, k.bio * s.cr_species AS cr, s.likely_species
FROM keyed k
LEFT JOIN best s USING (body)
WHERE k.bio > 0
ORDER BY cr DESC NULLS LAST, k.body

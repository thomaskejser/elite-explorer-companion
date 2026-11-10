INSERT INTO transform.system_exobio
WITH candidate AS (
    SELECT b.system_id, b.body, b.status, b.updated,
           coalesce(CASE WHEN o.bodies >= 200 THEN o.p_bio END, w.p_bio) AS p_bio,
           coalesce(CASE WHEN o.codexed_bodies >= 20 THEN o.cr_species END, w.cr_species) AS cr_species,
           coalesce(CASE WHEN o.bodies >= 200 THEN o.cr_bio END, w.cr_bio) AS cr_bio,
           coalesce(CASE WHEN o.codexed_bodies >= 20 THEN o.likely_species END, w.likely_species) AS likely_species,
           b.bio_signals
    FROM transform.exobio_body b
    LEFT JOIN main.exobio_odds o
      ON o.atmosphere = b.atmosphere AND o.body_type = b.body_type
     AND o.temp_band = b.temp_band AND o.star = b.star
    LEFT JOIN main.exobio_odds w
      ON w.atmosphere = b.atmosphere AND w.body_type = b.body_type
     AND w.temp_band = b.temp_band AND w.star = '*'
    WHERE b.status IN ('unmapped', 'pre_odyssey', 'stale_landable')
      AND abs((b.system_id >> 3) % $1) = $2
),
valued AS (
    SELECT *, CAST(round(CASE WHEN status = 'unmapped' THEN bio_signals * cr_species
                              ELSE p_bio * cr_bio END) AS BIGINT) AS cr_body
    FROM candidate
),
worked AS (
    SELECT system_id, count(*) AS n
    FROM transform.exobio_body
    WHERE status IN ('codexed', 'mapped')
      AND abs((system_id >> 3) % $1) = $2
    GROUP BY 1
),
per_system AS (
    SELECT system_id,
           count(*) AS candidate_bodies,
           count(*) FILTER (WHERE status = 'unmapped') AS unmapped_bodies,
           sum(coalesce(cr_body, 0)) AS cr_expected,
           arg_max(body, (coalesce(cr_body, 0), body)) AS best_body,
           max(coalesce(cr_body, 0)) AS best_cr,
           arg_max(likely_species, (coalesce(cr_body, 0), body)) AS best_species,
           max(updated) AS last_reported
    FROM valued
    GROUP BY 1
    HAVING sum(coalesce(cr_body, 0)) >= 10000000
)
SELECT p.system_id,
       CASE WHEN k.sector_id = 0 OR sc.sector IS NULL THEN k.system_in_sector
            ELSE sc.sector || ' ' || k.system_in_sector END,
       k.x, k.y, k.z,
       p.candidate_bodies, p.unmapped_bodies, coalesce(w.n, 0),
       p.cr_expected, p.best_body, p.best_cr, p.best_species, p.last_reported
FROM per_system p
JOIN main.system_known k ON k.system_id = p.system_id
                        AND abs((k.system_id >> 3) % $1) = $2
LEFT JOIN main.sector sc ON sc.sector_id = k.sector_id
LEFT JOIN worked w ON w.system_id = p.system_id;

INSERT INTO transform.exobio_body
WITH latest AS (
    SELECT * FROM transform.exobio_feed
    WHERE abs((system_id64 >> 3) % $1) = $2
    QUALIFY row_number() OVER (PARTITION BY system_id64, name
                               ORDER BY updated DESC, has_genus DESC,
                                        signal_biology DESC NULLS LAST,
                                        is_landable DESC NULLS LAST,
                                        surface_temp_k, sub_type, atmosphere_type) = 1
),
codexed AS (
    SELECT DISTINCT id64 AS system_id64, body AS name
    FROM staging.canonn_codex_event
    WHERE hud_category = 'Biology' AND body IS NOT NULL
      AND abs((id64 >> 3) % $1) = $2
),
arrival AS (
    SELECT k.system_id, b.code
    FROM main.system_known k
    JOIN main.body b ON b.body_id = k.primary_star_body_id
    WHERE abs((k.system_id >> 3) % $1) = $2
)
SELECT l.system_id64, l.name, l.sub_type, l.atmosphere_type, l.surface_temp_k,
       CAST(least(greatest(floor(l.surface_temp_k / 20) * 20, 100), 440) AS INTEGER),
       coalesce(a.code, '?'), l.is_landable, l.signal_biology, l.updated,
       CASE WHEN c.name IS NOT NULL THEN 'codexed'
            WHEN l.has_genus THEN 'mapped'
            WHEN l.signal_biology > 0 THEN 'unmapped'
            WHEN l.updated < TIMESTAMPTZ '2021-05-19 00:00:00+00' THEN 'pre_odyssey'
            WHEN l.is_landable IS NOT TRUE THEN 'stale_landable'
            ELSE 'unreported' END
FROM latest l
LEFT JOIN codexed c USING (system_id64, name)
LEFT JOIN arrival a ON a.system_id = l.system_id64;

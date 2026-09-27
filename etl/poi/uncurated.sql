WITH feed AS (
    SELECT english_name AS poi, 'canonn' AS src
    FROM staging.canonn_codex_event
    WHERE hud_category IN ('Cloud', 'Anomaly', 'Guardian', 'Thargoid')
       OR (hud_category = 'Tourist'
           AND lower(english_name) LIKE '%green%'
           AND lower(english_name) LIKE '%giant%')
    UNION ALL
    SELECT name, 'edsm' FROM staging.edsm_codex_entry WHERE name = 'Green Gas Giant'
    UNION ALL
    SELECT type, 'gec' FROM staging.edastro_point_of_interest WHERE type IS NOT NULL
)
SELECT poi, string_agg(DISTINCT src, '+' ORDER BY src) AS sources, count(*) AS reports
FROM feed
WHERE poi IS NOT NULL AND trim(poi) <> ''
  AND NOT EXISTS (SELECT 1 FROM transform.poi p WHERE p.poi = feed.poi)
GROUP BY poi
ORDER BY reports DESC;

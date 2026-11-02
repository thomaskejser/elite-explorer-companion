UPDATE system_outcome AS o
SET scanned_stars = list_distinct(list_append(o.scanned_stars, s.body)),
    {{FOUND_UPDATE}},
    updated_utc = now()
FROM (SELECT ?::VARCHAR AS system, ?::VARCHAR AS body, ?::VARCHAR AS cls) s
WHERE o.system = s.system

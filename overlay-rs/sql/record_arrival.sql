SELECT count(*) FROM system_visited WHERE system = ?;
INSERT INTO system_visited (system, id64, sector, first_visited_utc, last_visited_utc)
VALUES (?, NULL, nullif(regexp_extract(?, '^(.*) [A-Z][A-Z]-[A-Z] [a-h]\d', 1), ''),
        try_cast(? AS TIMESTAMP), try_cast(? AS TIMESTAMP));
UPDATE system_visited SET last_visited_utc = try_cast(? AS TIMESTAMP) WHERE system = ?;
SELECT count(*) FROM poi_visited WHERE system = ?;
INSERT INTO poi_visited (system, id64, sector, poi_id, poi, poi_class, visited_utc)
VALUES (?, NULL, nullif(regexp_extract(?, '^(.*) [A-Z][A-Z]-[A-Z] [a-h]\d', 1), ''), ?, ?, ?,
        try_cast(? AS TIMESTAMP));

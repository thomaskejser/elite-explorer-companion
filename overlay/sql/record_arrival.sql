SELECT count(*) FROM system_visited WHERE system = ?;
INSERT INTO system_visited (system, system_id, sector, first_visited_utc, last_visited_utc)
VALUES (?, NULL, nullif(regexp_extract(?, {{PROCEDURAL}}, 1), ''),
        try_cast(? AS TIMESTAMPTZ), try_cast(? AS TIMESTAMPTZ));
UPDATE system_visited SET last_visited_utc = try_cast(? AS TIMESTAMPTZ) WHERE system = ?;
SELECT count(*) FROM poi_visited WHERE system = ?;
INSERT INTO poi_visited (system, system_id, sector, poi_id, poi, poi_class, visited_utc)
VALUES (?, NULL, nullif(regexp_extract(?, {{PROCEDURAL}}, 1), ''), ?, ?, ?,
        try_cast(? AS TIMESTAMPTZ));

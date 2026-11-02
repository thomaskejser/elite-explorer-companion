SELECT count(*) FROM system_wrong WHERE system = ?;
INSERT INTO system_wrong (system, source, sector, system_id, marked_utc, note)
VALUES (?, ?, coalesce(?, nullif(regexp_extract(?, {{PROCEDURAL}}, 1), '')),
        NULL, try_cast(? AS TIMESTAMPTZ), ?);

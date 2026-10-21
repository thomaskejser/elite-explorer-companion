SELECT count(*) FROM system_wrong WHERE system = ?;
INSERT INTO system_wrong (system, source, sector, id64, marked_utc, note)
VALUES (?, ?, coalesce(?, nullif(regexp_extract(?, '^(.*) [A-Z][A-Z]-[A-Z] [a-h]\d', 1), '')),
        NULL, ?, ?);

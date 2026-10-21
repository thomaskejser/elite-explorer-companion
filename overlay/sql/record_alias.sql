CREATE TABLE IF NOT EXISTS system_alias (
    system       VARCHAR NOT NULL,
    canonical    VARCHAR NOT NULL,
    id64         BIGINT,
    x DOUBLE, y DOUBLE, z DOUBLE,
    star_class   VARCHAR,
    asserted_utc VARCHAR
);
SELECT system FROM system_alias WHERE canonical = ? AND system <> ?;
DELETE FROM system_alias WHERE system = ?;
INSERT INTO system_alias (system, canonical, id64, x, y, z, star_class, asserted_utc)
VALUES (?, ?, ?, ?, ?, ?, ?, ?);

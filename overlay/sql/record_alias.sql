CREATE TABLE IF NOT EXISTS system_alias (
    system       VARCHAR NOT NULL,
    canonical    VARCHAR NOT NULL,
    system_id    BIGINT,
    x DOUBLE, y DOUBLE, z DOUBLE,
    star_class   VARCHAR,
    asserted_utc TIMESTAMPTZ
);
SELECT system FROM system_alias WHERE canonical = ? AND system <> ?;
DELETE FROM system_alias WHERE system = ?;
INSERT INTO system_alias (system, canonical, system_id, x, y, z, star_class, asserted_utc)
VALUES (?, ?, ?, ?, ?, ?, ?, try_cast(? AS TIMESTAMPTZ));

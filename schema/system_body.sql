-- system_body: every body we know exists. Load order tier 3 (needs system_known).
--
-- *** PRIMARY KEY ONLY. NO FOREIGN KEYS, NO UNIQUE. *** This is a measured limit of
-- the hardware, not a design preference. Copying all 570,812,803 rows on a 33.5GB
-- machine:
--
--     no constraints                              134s
--     PRIMARY KEY only                            738s     <-- what this file declares
--     PRIMARY KEY + UNIQUE(system_id,system_body) OOM at 14.9GiB after 898s
--     PRIMARY KEY + 3 FOREIGN KEYs                OOM at 24.2GiB
--
-- Every secondary constraint builds its own ART index over 570.8M rows, and DuckDB
-- must pin those blocks to commit. For contrast system_known, at 197.6M rows, carries
-- a PRIMARY KEY, a composite UNIQUE and FOUR foreign keys without trouble -- so the
-- wall sits between those two sizes, not at "system_body is special".
--
-- WHAT STILL PROTECTS THIS TABLE:
--   * system_id -> system_known and body_id -> body are enforced by construction:
--     build_system_body.py only ever inserts rows it resolved through those tables.
--   * the natural key (system_id, system_body) is enforced by that builder's
--     `INSERT ... WHERE NOT EXISTS` merge.
--   * INVARIANT, at most one is_primary row per system_id, resolved by the cascade in
--     build_system_body.py.
-- None of the three is enforced by the DATABASE here. Verify them by query after any
-- load that bypasses the builder; scripts/verify_new_model.py does exactly that.
CREATE TABLE IF NOT EXISTS system_body (
    system_body_id   BIGINT  NOT NULL PRIMARY KEY,
    system_id        BIGINT  NOT NULL,
    body_id          INTEGER,
    system_body      VARCHAR NOT NULL,
    is_primary       BOOLEAN NOT NULL,
    discovered_time  TIMESTAMP,
    solar_masses     DOUBLE,
    earth_masses     DOUBLE,
    is_terraformable BOOLEAN,
    source           VARCHAR,
    id_poi           INTEGER
);

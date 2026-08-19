-- system_phenomenon: catalogued notable phenomena, grain (system_id, phenomenon).
-- Load order tier 3 (needs system_known). RECORDS -- merges, never deletes.
CREATE TABLE IF NOT EXISTS system_phenomenon (
    system_phenomenon_id BIGINT PRIMARY KEY,
    system_id            BIGINT NOT NULL REFERENCES system_known (system_id),
    phenomenon           VARCHAR NOT NULL,
    kinds                VARCHAR,
    observations         INTEGER,
    first_reported       TIMESTAMP,
    last_reported        TIMESTAMP,
    from_canonn          BOOLEAN,
    from_edsm            BOOLEAN,
    from_gec             BOOLEAN
);

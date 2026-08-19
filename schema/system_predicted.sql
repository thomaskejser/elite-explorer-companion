-- system_predicted: per-system target probabilities. Load order tier 3.
-- NO foreign key to system_known ON PURPOSE: the boxel-predicted rows (is_catalog
-- FALSE) describe systems that are in no dump and therefore have no system_known
-- parent. PREDICTS -- it is the one table allowed to DELETE (see ETL.md 3).
-- is_catalog is LAST because it replaced a VARCHAR `source` column via ALTER TABLE
-- ADD COLUMN, which can only append; moving it up would make a fresh database
-- disagree with a migrated one under DESCRIBE.
CREATE TABLE IF NOT EXISTS system_predicted (
    system_predicted_id BIGINT  NOT NULL PRIMARY KEY,
    system_name         VARCHAR NOT NULL,
    system_id64         BIGINT,
    mass_code           VARCHAR NOT NULL,
    sector              VARCHAR,
    boxel               VARCHAR,
    x DOUBLE, y DOUBLE, z DOUBLE,
    plane_r DOUBLE, r_sgra DOUBLE, dist_sol DOUBLE,
    p_bh DOUBLE, p_wr DOUBLE,
    p_bh_model DOUBLE, p_wr_model DOUBLE,
    p_hr DOUBLE,
    p_neutron DOUBLE, p_wd DOUBLE, p_herbig DOUBLE,
    p_otype DOUBLE, p_supergiant DOUBLE,
    exp_bodies DOUBLE, exp_scan_value_cr DOUBLE,
    is_catalog BOOLEAN NOT NULL,
    UNIQUE (system_name)
);

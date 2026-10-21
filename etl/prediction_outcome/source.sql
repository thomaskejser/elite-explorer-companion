CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.prediction_source;

CREATE TABLE transform.prediction_source AS
SELECT system, is_catalog, system_id, sector, mass_code, x, y, z,
       p_bh, p_wr, p_neutron, p_wd, p_herbig, p_otype, p_supergiant, exp_bodies,
       predicted_in
FROM (${sources})
QUALIFY row_number() OVER (PARTITION BY system, is_catalog ORDER BY taken DESC) = 1;

COMMENT ON TABLE transform.prediction_source IS
'TRANSFORM: every prediction main.system_predicted and the staging.pred_snapshot_* tables hold, one row per (system, is_catalog) from the latest of them. Input to transform.prediction_outcome. Rebuilt on every load, safe to drop.';

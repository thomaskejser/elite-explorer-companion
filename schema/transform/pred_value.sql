CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.pred_value;

CREATE TABLE transform.pred_value (
    mass_code         VARCHAR NOT NULL PRIMARY KEY,
    n                 BIGINT  NOT NULL,
    exp_bodies        DOUBLE,
    exp_scan_value_cr DOUBLE,
    completeness      DOUBLE
);

INSERT INTO transform.pred_value
WITH comp AS (
    SELECT sum(v.n_bodies)::DOUBLE / nullif(sum(k.body_count), 0) AS c
    FROM staging.sys_value v
    JOIN main.system_known k USING (system_id)
    WHERE k.body_count IS NOT NULL
)
SELECT k.mass_code, count(*),
       avg(v.n_bodies),
       avg(v.base_cr) / (SELECT c FROM comp),
       (SELECT c FROM comp)
FROM staging.sys_value v
JOIN main.system_known k USING (system_id)
WHERE k.mass_code IN ('e', 'f', 'g', 'h')
GROUP BY 1;

COMMENT ON TABLE transform.pred_value IS
'TRANSFORM: expected body count and full-scan value per boxel mass code, from staging.sys_value. Rebuilt on every main.system_predicted load, safe to drop.

The value is scaled up by 1 / completeness, where completeness = reported bodies / declared body_count over systems with both -- the correction from "value of what was reported" to "value of a full scan". A per-mass-code AVERAGE, never a per-system fact.';

COMMENT ON COLUMN transform.pred_value.mass_code IS 'Boxel mass code, e to h.';
COMMENT ON COLUMN transform.pred_value.n IS 'Systems with body rows in this mass code.';
COMMENT ON COLUMN transform.pred_value.exp_bodies IS 'Mean REPORTED body rows per system. Not corrected for completeness, so a lower bound.';
COMMENT ON COLUMN transform.pred_value.exp_scan_value_cr IS 'Mean base_cr divided by completeness: an estimated full-scan credit value. Unrounded here; rounded to 2 dp where it reaches main.';
COMMENT ON COLUMN transform.pred_value.completeness IS 'Galaxy-wide reported / declared body ratio, the same value on every row. Printed by the loader.';

CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.system_predicted;

CREATE TABLE transform.system_predicted (
    system_predicted_id BIGINT  NOT NULL,
    system              VARCHAR NOT NULL PRIMARY KEY,
    system_id64         BIGINT,
    is_catalog          BOOLEAN NOT NULL,
    mass_code           VARCHAR NOT NULL,
    sector              VARCHAR,
    boxel               VARCHAR,
    x                   DOUBLE,
    y                   DOUBLE,
    z                   DOUBLE,
    plane_r             DOUBLE,
    r_sgra              DOUBLE,
    dist_sol            DOUBLE,
    p_bh                DOUBLE,
    p_wr                DOUBLE,
    p_neutron           DOUBLE,
    p_wd                DOUBLE,
    p_herbig            DOUBLE,
    p_otype             DOUBLE,
    p_supergiant        DOUBLE,
    exp_bodies          DOUBLE,
    exp_scan_value_cr   DOUBLE
);

INSERT INTO transform.system_predicted
    (system_predicted_id, system, system_id64, is_catalog, mass_code, sector, boxel,
     x, y, z, plane_r, r_sgra, dist_sol, p_bh, p_wr, p_neutron, p_wd, p_herbig,
     p_otype, p_supergiant, exp_bodies, exp_scan_value_cr)
WITH scored AS (
  SELECT p.system_name AS system, p.system_id64, p.is_catalog, p.mass_code, p.sector,
         p.boxel, p.x, p.y, p.z,
         round(p.plane_r, 3) AS plane_r, round(p.r_sgra, 3) AS r_sgra,
         round(sqrt(p.x*p.x + p.y*p.y + p.z*p.z), 3) AS dist_sol,
         round(r.r_bh         * coalesce(xf.f_bh, 1.0), 6)         AS p_bh,
         round(r.r_wr         * coalesce(xf.f_wr, 1.0), 6)         AS p_wr,
         round(r.r_neutron    * coalesce(xf.f_neutron, 1.0), 6)    AS p_neutron,
         round(r.r_wd         * coalesce(xf.f_wd, 1.0), 6)         AS p_wd,
         round(r.r_herbig     * coalesce(xf.f_herbig, 1.0), 6)     AS p_herbig,
         round(r.r_otype      * coalesce(xf.f_otype, 1.0), 6)      AS p_otype,
         round(r.r_supergiant * coalesce(xf.f_supergiant, 1.0), 6) AS p_supergiant,
         round(v.exp_bodies, 3)        AS exp_bodies,
         round(v.exp_scan_value_cr, 2) AS exp_scan_value_cr
  FROM transform.pred_pool p
  LEFT JOIN transform.pred_rate r
    ON r.mass_code = p.mass_code
   AND r.band = CASE WHEN p.plane_r < 10000 THEN '0-10k'
                     WHEN p.plane_r < 20000 THEN '10-20k'
                     WHEN p.plane_r < 30000 THEN '20-30k'
                     ELSE '30k+' END
  LEFT JOIN transform.pred_cross xf
    ON xf.cross_band = CASE WHEN least(abs(p.x), abs(p.z)) < 100  THEN '0-100'
                            WHEN least(abs(p.x), abs(p.z)) < 200  THEN '100-200'
                            WHEN least(abs(p.x), abs(p.z)) < 400  THEN '200-400'
                            WHEN least(abs(p.x), abs(p.z)) < 600  THEN '400-600'
                            WHEN least(abs(p.x), abs(p.z)) < 800  THEN '600-800'
                            WHEN least(abs(p.x), abs(p.z)) < 1000 THEN '800-1000'
                            WHEN least(abs(p.x), abs(p.z)) < 1200 THEN '1000-1200'
                            WHEN least(abs(p.x), abs(p.z)) < 1400 THEN '1200-1400'
                            WHEN least(abs(p.x), abs(p.z)) < 1600 THEN '1400-1600'
                            WHEN least(abs(p.x), abs(p.z)) < 2000 THEN '1600-2000'
                            ELSE 'clear' END
  LEFT JOIN transform.pred_value v ON v.mass_code = p.mass_code
)
SELECT coalesce(t.system_predicted_id,
                (SELECT coalesce(max(system_predicted_id), 0) FROM main.system_predicted)
                + row_number() OVER (PARTITION BY t.system_predicted_id IS NULL
                                     ORDER BY s.system)),
       s.system, s.system_id64, s.is_catalog, s.mass_code, s.sector, s.boxel,
       s.x, s.y, s.z, s.plane_r, s.r_sgra, s.dist_sol,
       s.p_bh, s.p_wr, s.p_neutron, s.p_wd, s.p_herbig, s.p_otype, s.p_supergiant,
       s.exp_bodies, s.exp_scan_value_cr
FROM scored s
LEFT JOIN main.system_predicted t ON t.system = s.system;

COMMENT ON TABLE transform.system_predicted IS
'TRANSFORM: transform.pred_pool scored -- base rate from transform.pred_rate times the cross factor from transform.pred_cross, plus the expected value from transform.pred_value -- shaped exactly as main.system_predicted merges it. Rebuilt on every load, safe to drop.

Every probability and distance is ROUNDED here (6 dp and 3 dp). That is what makes the merge idempotent: the rates are float aggregates whose last bits move between runs, and unrounded they report millions of spurious updates.

system_predicted_id is carried over for a name already in main and allocated max+1 for a new one. A row main holds that is absent here is DELETED by the loader -- see the main table''s comment.';

COMMENT ON COLUMN transform.system_predicted.system_predicted_id IS 'Surrogate id, copied from main when the name exists, else allocated above the current maximum. Never the merge key.';
COMMENT ON COLUMN transform.system_predicted.system IS 'Full system name -- the natural key the merge matches on. PRIMARY KEY here, so a duplicate fails before main.';
COMMENT ON COLUMN transform.system_predicted.system_id64 IS 'The game''s id64, NULL for a boxel-predicted row.';
COMMENT ON COLUMN transform.system_predicted.is_catalog IS 'TRUE: known but unscanned. FALSE: predicted from a boxel gap.';
COMMENT ON COLUMN transform.system_predicted.mass_code IS 'Boxel mass code, e to h.';
COMMENT ON COLUMN transform.system_predicted.sector IS 'Sector name.';
COMMENT ON COLUMN transform.system_predicted.boxel IS 'Boxel grouping key, see transform.pred_pool.boxel.';
COMMENT ON COLUMN transform.system_predicted.x IS 'Galactic x, ly, as pooled.';
COMMENT ON COLUMN transform.system_predicted.y IS 'Galactic y, ly, as pooled.';
COMMENT ON COLUMN transform.system_predicted.z IS 'Galactic z, ly, as pooled.';
COMMENT ON COLUMN transform.system_predicted.plane_r IS 'x/z-plane distance from Sgr A*, 3 dp.';
COMMENT ON COLUMN transform.system_predicted.r_sgra IS '3-D distance from Sgr A*, 3 dp.';
COMMENT ON COLUMN transform.system_predicted.dist_sol IS 'Distance from Sol, 3 dp.';
COMMENT ON COLUMN transform.system_predicted.p_bh IS 'Black-hole probability, 6 dp: base rate times cross factor. A ranking score from reported bodies, a lower bound, not a calibrated chance.';
COMMENT ON COLUMN transform.system_predicted.p_wr IS 'Wolf-Rayet probability, 6 dp. See p_bh.';
COMMENT ON COLUMN transform.system_predicted.p_neutron IS 'Neutron-star probability, 6 dp. See p_bh.';
COMMENT ON COLUMN transform.system_predicted.p_wd IS 'White-dwarf probability, 6 dp. See p_bh.';
COMMENT ON COLUMN transform.system_predicted.p_herbig IS 'Herbig Ae/Be probability, 6 dp. See p_bh.';
COMMENT ON COLUMN transform.system_predicted.p_otype IS 'O-type probability, 6 dp. See p_bh.';
COMMENT ON COLUMN transform.system_predicted.p_supergiant IS 'Supergiant probability, 6 dp. See p_bh.';
COMMENT ON COLUMN transform.system_predicted.exp_bodies IS 'Mean reported bodies for the mass code, 3 dp. A lower bound.';
COMMENT ON COLUMN transform.system_predicted.exp_scan_value_cr IS 'Estimated full-scan credits for the mass code, 2 dp. A per-mass-code average.';

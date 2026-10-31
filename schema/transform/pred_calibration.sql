CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.pred_calibration;

CREATE TABLE transform.pred_calibration (
    mass_code      VARCHAR NOT NULL,
    band           VARCHAR NOT NULL,
    n              BIGINT  NOT NULL,
    obs_bh         BIGINT  NOT NULL, exp_bh         DOUBLE, c_bh         DOUBLE NOT NULL,
    obs_wr         BIGINT  NOT NULL, exp_wr         DOUBLE, c_wr         DOUBLE NOT NULL,
    obs_neutron    BIGINT  NOT NULL, exp_neutron    DOUBLE, c_neutron    DOUBLE NOT NULL,
    obs_wd         BIGINT  NOT NULL, exp_wd         DOUBLE, c_wd         DOUBLE NOT NULL,
    obs_herbig     BIGINT  NOT NULL, exp_herbig     DOUBLE, c_herbig     DOUBLE NOT NULL,
    obs_otype      BIGINT  NOT NULL, exp_otype      DOUBLE, c_otype      DOUBLE NOT NULL,
    obs_supergiant BIGINT  NOT NULL, exp_supergiant DOUBLE, c_supergiant DOUBLE NOT NULL,
    PRIMARY KEY (mass_code, band)
);

INSERT INTO transform.pred_calibration
WITH located AS (
  SELECT o.*,
         least(abs(o.x), abs(o.z)) AS cross_d,
         sqrt(pow(o.x - 25.21875, 2) + pow(o.z - 25899.96875, 2)) AS plane_r
  FROM main.prediction_outcome o
  WHERE o.revealed_by = 'survey' AND o.mass_code IN ('e', 'f', 'g', 'h')
    AND o.surveyed_bodies >= o.exp_bodies
    AND o.x IS NOT NULL AND o.z IS NOT NULL
),
banded AS (
  SELECT *,
         CASE WHEN cross_d < 100  THEN '0-100'
              WHEN cross_d < 200  THEN '100-200'
              WHEN cross_d < 400  THEN '200-400'
              WHEN cross_d < 600  THEN '400-600'
              WHEN cross_d < 800  THEN '600-800'
              WHEN cross_d < 1000 THEN '800-1000'
              WHEN cross_d < 1200 THEN '1000-1200'
              WHEN cross_d < 1400 THEN '1200-1400'
              WHEN cross_d < 1600 THEN '1400-1600'
              WHEN cross_d < 2000 THEN '1600-2000'
              ELSE 'clear' END AS cross_band,
         CASE WHEN plane_r < 10000 THEN '0-10k'
              WHEN plane_r < 20000 THEN '10-20k'
              WHEN plane_r < 30000 THEN '20-30k'
              ELSE '30k+' END AS band
  FROM located
),
m AS (
  SELECT b.mass_code, b.band, count(*) AS n,
         sum(b.found_bh::INTEGER)         AS obs_bh,         sum(r.r_bh         * x.f_bh)         AS exp_bh,
         sum(b.found_wr::INTEGER)         AS obs_wr,         sum(r.r_wr         * x.f_wr)         AS exp_wr,
         sum(b.found_neutron::INTEGER)    AS obs_neutron,    sum(r.r_neutron    * x.f_neutron)    AS exp_neutron,
         sum(b.found_wd::INTEGER)         AS obs_wd,         sum(r.r_wd         * x.f_wd)         AS exp_wd,
         sum(b.found_herbig::INTEGER)     AS obs_herbig,     sum(r.r_herbig     * x.f_herbig)     AS exp_herbig,
         sum(b.found_otype::INTEGER)      AS obs_otype,      sum(r.r_otype      * x.f_otype)      AS exp_otype,
         sum(b.found_supergiant::INTEGER) AS obs_supergiant, sum(r.r_supergiant * x.f_supergiant) AS exp_supergiant
  FROM banded b
  JOIN transform.pred_rate r ON r.mass_code = b.mass_code AND r.band = b.band
  JOIN transform.pred_cross x ON x.cross_band = b.cross_band
  GROUP BY 1, 2
)
SELECT mass_code, band, n,
       obs_bh,         round(exp_bh, 3),         least(round((obs_bh + 20)         / (coalesce(exp_bh, 0) + 20), 4), 1.0),
       obs_wr,         round(exp_wr, 3),         least(round((obs_wr + 20)         / (coalesce(exp_wr, 0) + 20), 4), 1.0),
       obs_neutron,    round(exp_neutron, 3),    least(round((obs_neutron + 20)    / (coalesce(exp_neutron, 0) + 20), 4), 1.0),
       obs_wd,         round(exp_wd, 3),         least(round((obs_wd + 20)         / (coalesce(exp_wd, 0) + 20), 4), 1.0),
       obs_herbig,     round(exp_herbig, 3),     least(round((obs_herbig + 20)     / (coalesce(exp_herbig, 0) + 20), 4), 1.0),
       obs_otype,      round(exp_otype, 3),      least(round((obs_otype + 20)      / (coalesce(exp_otype, 0) + 20), 4), 1.0),
       obs_supergiant, round(exp_supergiant, 3), least(round((obs_supergiant + 20) / (coalesce(exp_supergiant, 0) + 20), 4), 1.0)
FROM m;

COMMENT ON TABLE transform.pred_calibration IS
'TRANSFORM: the out-of-sample RECALIBRATION of every p_* in main.system_predicted, one factor per (mass_code, plane_r band) and target, measured on main.prediction_outcome. Rebuilt on every main.system_predicted load, after transform.pred_rate and transform.pred_cross, so every refresh recalibrates against every prediction resolved so far. Safe to drop.

ONLY FULLY SURVEYED OUTCOMES COUNT: revealed_by = ''survey'' and surveyed_bodies >= the frozen exp_bodies. A system resolved by one honk reports its primary and little else, so it hides every companion target (black holes in h read 0.11x expected that way, 0.85x on surveyed systems).

EXPECTED IS TODAY''S MODEL, NOT THE FROZEN P. Each resolved system is rescored with the current base rate times its cross factor, without p_exist (a system the survey revealed exists), and that sum is compared with the targets found there. The frozen prediction_outcome.p_* are not used: they come from whichever model version made them, so dividing by them would correct today''s model for an older one''s mistakes.

c_<target> = least((found + 20) / (expected + 20), 1.0): the observed/expected ratio shrunk toward 1.0 by 20 pseudo-hits, so a cell with few resolved systems or a rare target barely moves, and CAPPED AT 1.0. 1.0 where nothing has resolved: a (mass_code, band) cell absent here is not calibrated.

*** THE CAP IS THE SELECTION BIAS. *** The galaxy map shows a system''s primary class, so commanders fly to the targets it shows: 2,673 of the 2,898 Wolf-Rayets and 1,837 of the 2,255 e-mass neutrons found in resolved systems are the primary, and neutron routes hop through exactly those. Found therefore runs ABOVE the truth wherever the target can be the primary (e neutrons read 13x expected even on surveyed systems), and an excess is no evidence the model is low. A shortfall survives that bias, so the calibration only ever lowers a rate.';

COMMENT ON COLUMN transform.pred_calibration.mass_code IS 'Boxel mass code, e to h.';
COMMENT ON COLUMN transform.pred_calibration.band IS 'Band of distance from the galactic centre in the x/z plane, as transform.pred_rate.band.';
COMMENT ON COLUMN transform.pred_calibration.n IS 'Fully surveyed resolved predictions in the cell behind every factor.';
COMMENT ON COLUMN transform.pred_calibration.obs_bh IS 'Resolved systems in the cell where a black hole was reported.';
COMMENT ON COLUMN transform.pred_calibration.exp_bh IS 'Black holes today''s uncalibrated model expects over the same systems: base rate times cross factor, summed, 3 dp.';
COMMENT ON COLUMN transform.pred_calibration.c_bh IS 'Calibration factor on p_bh: least((obs_bh + 20) / (exp_bh + 20), 1.0), 4 dp.';
COMMENT ON COLUMN transform.pred_calibration.obs_wr IS 'Same as obs_bh, for Wolf-Rayet.';
COMMENT ON COLUMN transform.pred_calibration.exp_wr IS 'Same as exp_bh, for Wolf-Rayet.';
COMMENT ON COLUMN transform.pred_calibration.c_wr IS 'Same as c_bh, for p_wr.';
COMMENT ON COLUMN transform.pred_calibration.obs_neutron IS 'Same as obs_bh, for neutron stars.';
COMMENT ON COLUMN transform.pred_calibration.exp_neutron IS 'Same as exp_bh, for neutron stars.';
COMMENT ON COLUMN transform.pred_calibration.c_neutron IS 'Same as c_bh, for p_neutron.';
COMMENT ON COLUMN transform.pred_calibration.obs_wd IS 'Same as obs_bh, for white dwarfs.';
COMMENT ON COLUMN transform.pred_calibration.exp_wd IS 'Same as exp_bh, for white dwarfs.';
COMMENT ON COLUMN transform.pred_calibration.c_wd IS 'Same as c_bh, for p_wd.';
COMMENT ON COLUMN transform.pred_calibration.obs_herbig IS 'Same as obs_bh, for Herbig Ae/Be.';
COMMENT ON COLUMN transform.pred_calibration.exp_herbig IS 'Same as exp_bh, for Herbig Ae/Be.';
COMMENT ON COLUMN transform.pred_calibration.c_herbig IS 'Same as c_bh, for p_herbig.';
COMMENT ON COLUMN transform.pred_calibration.obs_otype IS 'Same as obs_bh, for O-type stars.';
COMMENT ON COLUMN transform.pred_calibration.exp_otype IS 'Same as exp_bh, for O-type stars.';
COMMENT ON COLUMN transform.pred_calibration.c_otype IS 'Same as c_bh, for p_otype.';
COMMENT ON COLUMN transform.pred_calibration.obs_supergiant IS 'Same as obs_bh, for supergiants.';
COMMENT ON COLUMN transform.pred_calibration.exp_supergiant IS 'Same as exp_bh, for supergiants.';
COMMENT ON COLUMN transform.pred_calibration.c_supergiant IS 'Same as c_bh, for p_supergiant.';

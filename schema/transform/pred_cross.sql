CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.pred_cross;

CREATE TABLE transform.pred_cross (
    cross_band   VARCHAR NOT NULL PRIMARY KEY,
    lo           DOUBLE,
    n            BIGINT  NOT NULL,
    f_bh         DOUBLE  NOT NULL,
    f_wr         DOUBLE  NOT NULL,
    f_neutron    DOUBLE  NOT NULL,
    f_wd         DOUBLE  NOT NULL,
    f_herbig     DOUBLE  NOT NULL,
    f_otype      DOUBLE  NOT NULL,
    f_supergiant DOUBLE  NOT NULL
);

INSERT INTO transform.pred_cross
WITH located AS (
  SELECT least(abs(k.x), abs(k.z)) AS cross_d,
         sqrt(pow(k.x - 25.21875, 2) + pow(k.z - 25899.96875, 2)) AS plane_r,
         k.mass_code,
         l.has_bh, l.has_wr, l.has_neutron, l.has_wd, l.has_herbig, l.has_otype,
         l.has_supergiant
  FROM transform.pred_labels l
  JOIN main.system_known k ON k.system_id = l.system_id
  WHERE k.mass_code IN ('e', 'f', 'g', 'h') AND l.n_scan_rows > 0 AND l.n_stars > 0
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
  SELECT b.cross_band, min(b.cross_d) AS lo, count(*) AS n,
         sum(b.has_bh::int)         AS obs_bh,         sum(r.r_bh)         AS exp_bh,
         sum(b.has_wr::int)         AS obs_wr,         sum(r.r_wr)         AS exp_wr,
         sum(b.has_neutron::int)    AS obs_neutron,    sum(r.r_neutron)    AS exp_neutron,
         sum(b.has_wd::int)         AS obs_wd,         sum(r.r_wd)         AS exp_wd,
         sum(b.has_herbig::int)     AS obs_herbig,     sum(r.r_herbig)     AS exp_herbig,
         sum(b.has_otype::int)      AS obs_otype,      sum(r.r_otype)      AS exp_otype,
         sum(b.has_supergiant::int) AS obs_supergiant, sum(r.r_supergiant) AS exp_supergiant
  FROM banded b
  JOIN transform.pred_rate r ON r.mass_code = b.mass_code AND r.band = b.band
  GROUP BY 1
),
q AS (
  SELECT cross_band, lo, n,
         CASE WHEN exp_bh IS NULL OR exp_bh = 0 THEN NULL ELSE obs_bh / exp_bh END AS q_bh,
         CASE WHEN exp_wr IS NULL OR exp_wr = 0 THEN NULL ELSE obs_wr / exp_wr END AS q_wr,
         CASE WHEN exp_neutron IS NULL OR exp_neutron = 0 THEN NULL ELSE obs_neutron / exp_neutron END AS q_neutron,
         CASE WHEN exp_wd IS NULL OR exp_wd = 0 THEN NULL ELSE obs_wd / exp_wd END AS q_wd,
         CASE WHEN exp_herbig IS NULL OR exp_herbig = 0 THEN NULL ELSE obs_herbig / exp_herbig END AS q_herbig,
         CASE WHEN exp_otype IS NULL OR exp_otype = 0 THEN NULL ELSE obs_otype / exp_otype END AS q_otype,
         CASE WHEN exp_supergiant IS NULL OR exp_supergiant = 0 THEN NULL ELSE obs_supergiant / exp_supergiant END AS q_supergiant
  FROM m
),
c AS (
  SELECT *,
         max(q_bh) FILTER (WHERE cross_band = 'clear') OVER () AS c_bh,
         max(q_wr) FILTER (WHERE cross_band = 'clear') OVER () AS c_wr,
         max(q_neutron) FILTER (WHERE cross_band = 'clear') OVER () AS c_neutron,
         max(q_wd) FILTER (WHERE cross_band = 'clear') OVER () AS c_wd,
         max(q_herbig) FILTER (WHERE cross_band = 'clear') OVER () AS c_herbig,
         max(q_otype) FILTER (WHERE cross_band = 'clear') OVER () AS c_otype,
         max(q_supergiant) FILTER (WHERE cross_band = 'clear') OVER () AS c_supergiant
  FROM q
)
SELECT cross_band, lo, n,
       CASE WHEN q_bh IS NULL OR c_bh IS NULL OR c_bh = 0 THEN 1.0 WHEN q_bh = 0 THEN 0.0
            ELSE least(round(q_bh / c_bh, 6), 1.0) END,
       CASE WHEN q_wr IS NULL OR c_wr IS NULL OR c_wr = 0 THEN 1.0 WHEN q_wr = 0 THEN 0.0
            ELSE least(round(q_wr / c_wr, 6), 1.0) END,
       CASE WHEN q_neutron IS NULL OR c_neutron IS NULL OR c_neutron = 0 THEN 1.0 WHEN q_neutron = 0 THEN 0.0
            ELSE least(round(q_neutron / c_neutron, 6), 1.0) END,
       CASE WHEN q_wd IS NULL OR c_wd IS NULL OR c_wd = 0 THEN 1.0 WHEN q_wd = 0 THEN 0.0
            ELSE least(round(q_wd / c_wd, 6), 1.0) END,
       CASE WHEN q_herbig IS NULL OR c_herbig IS NULL OR c_herbig = 0 THEN 1.0 WHEN q_herbig = 0 THEN 0.0
            ELSE least(round(q_herbig / c_herbig, 6), 1.0) END,
       CASE WHEN q_otype IS NULL OR c_otype IS NULL OR c_otype = 0 THEN 1.0 WHEN q_otype = 0 THEN 0.0
            ELSE least(round(q_otype / c_otype, 6), 1.0) END,
       CASE WHEN q_supergiant IS NULL OR c_supergiant IS NULL OR c_supergiant = 0 THEN 1.0 WHEN q_supergiant = 0 THEN 0.0
            ELSE least(round(q_supergiant / c_supergiant, 6), 1.0) END
FROM c;

COMMENT ON TABLE transform.pred_cross IS
'TRANSFORM: the Stellar Forge CROSS -- how much the generator suppresses each rare target near the x=0 and z=0 planes, as a factor on transform.pred_rate, keyed by band of least(|x|,|z|). Measured as observed/expected over scanned e/f/g/h systems against rates fitted OUTSIDE the cross, divided by the same ratio in the clear band, so the clear band is 1.0 by construction. The division is needed because transform.pred_rate fits on near-completely explored boxels while this counts every scan, whose observed rates run higher everywhere. Rebuilt on every main.system_predicted load, safe to drop.

A 0.0 means the band observed none at all -- Wolf-Rayet is 0 against hundreds expected inside 1,200 ly, which is a generator rule rather than a small number. Factors are capped at 1.0: the cross only ever suppresses.';

COMMENT ON COLUMN transform.pred_cross.cross_band IS 'Band of least(|x|,|z|) in ly, 0-100 up to 1600-2000, then clear. A system with no coordinates falls in clear.';
COMMENT ON COLUMN transform.pred_cross.lo IS 'Smallest least(|x|,|z|) observed in the band. For ordering the report only.';
COMMENT ON COLUMN transform.pred_cross.n IS 'Scanned systems in the band behind every factor.';
COMMENT ON COLUMN transform.pred_cross.f_bh IS 'Observed / expected black holes over the same ratio in the clear band, 6 dp, capped at 1.0. 1.0 when nothing was expected.';
COMMENT ON COLUMN transform.pred_cross.f_wr IS 'Same for Wolf-Rayet.';
COMMENT ON COLUMN transform.pred_cross.f_neutron IS 'Same for neutron stars.';
COMMENT ON COLUMN transform.pred_cross.f_wd IS 'Same for white dwarfs.';
COMMENT ON COLUMN transform.pred_cross.f_herbig IS 'Same for Herbig Ae/Be.';
COMMENT ON COLUMN transform.pred_cross.f_otype IS 'Same for O-type stars.';
COMMENT ON COLUMN transform.pred_cross.f_supergiant IS 'Same for supergiants.';

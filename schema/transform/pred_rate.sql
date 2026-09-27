CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.pred_rate;

CREATE TABLE transform.pred_rate (
    mass_code    VARCHAR NOT NULL,
    band         VARCHAR NOT NULL,
    n            BIGINT  NOT NULL,
    r_bh         DOUBLE,
    r_wr         DOUBLE,
    wr_tier      INTEGER,
    wr_n         BIGINT,
    r_neutron    DOUBLE,
    r_wd         DOUBLE,
    r_herbig     DOUBLE,
    r_otype      DOUBLE,
    r_supergiant DOUBLE,
    PRIMARY KEY (mass_code, band)
);

INSERT INTO transform.pred_rate
WITH located AS (
  SELECT k.sector_id, k.cube_id, k.sub_cube_id, k.mass_code,
         sqrt(pow(k.x - 25.21875, 2) + pow(k.z - 25899.96875, 2)) AS plane_r,
         l.has_bh, l.has_wr, l.has_neutron, l.has_wd, l.has_herbig, l.has_otype,
         l.has_supergiant
  FROM transform.pred_labels l
  JOIN main.system_known k ON k.system_id = l.system_id
  WHERE k.mass_code IN ('e', 'f', 'g', 'h') AND l.n_scan_rows > 0 AND l.n_stars > 0
    AND least(abs(k.x), abs(k.z)) >= 2000
),
scanned AS (
  SELECT *,
         CASE WHEN plane_r < 10000 THEN '0-10k'
              WHEN plane_r < 20000 THEN '10-20k'
              WHEN plane_r < 30000 THEN '20-30k'
              ELSE '30k+' END AS band
  FROM located
),
wr_tier AS (
  SELECT s.mass_code, s.band, s.has_wr,
         CASE WHEN b.scanned >= 10 AND b.frac >= 0.90 THEN 1
              WHEN b.scanned >= 10 AND b.frac >= 0.80 THEN 2
              ELSE 3 END AS tier
  FROM scanned s JOIN transform.pred_boxel_scan b
    USING (sector_id, cube_id, mass_code, sub_cube_id)
),
wr_size AS (SELECT mass_code, band, tier, count(*) AS n FROM wr_tier GROUP BY 1, 2, 3),
wr_big  AS (SELECT mass_code, band, max(n) AS max_n FROM wr_size
            WHERE tier < 3 GROUP BY 1, 2),
wr_best AS (
  SELECT s.mass_code, s.band,
         coalesce(min(s.tier) FILTER (WHERE s.n >= 5000 AND s.tier < 3),
                  min(s.tier) FILTER (WHERE s.tier < 3 AND s.n = g.max_n),
                  3) AS use_tier
  FROM wr_size s LEFT JOIN wr_big g USING (mass_code, band)
  GROUP BY 1, 2
),
wr AS (
  SELECT t.mass_code, t.band, coalesce(w.use_tier, 3) AS wr_tier,
         count(*) AS wr_n, avg(t.has_wr) AS r_wr
  FROM wr_tier t LEFT JOIN wr_best w USING (mass_code, band)
  WHERE t.tier = coalesce(w.use_tier, 3)
  GROUP BY 1, 2, 3
)
SELECT s.mass_code, s.band, count(*),
       avg(s.has_bh),
       wr.r_wr,
       wr.wr_tier,
       wr.wr_n,
       avg(s.has_neutron),
       avg(s.has_wd),
       avg(s.has_herbig),
       avg(s.has_otype),
       avg(s.has_supergiant)
FROM scanned s LEFT JOIN wr USING (mass_code, band)
GROUP BY 1, 2, wr.r_wr, wr.wr_tier, wr.wr_n;

COMMENT ON TABLE transform.pred_rate IS
'TRANSFORM: the empirical base rate of each rare target per (mass_code, galactic-plane-radius band), fitted on SCANNED e/f/g/h systems OUTSIDE the cross (least(|x|,|z|) >= 2000 ly) so the cross suppression in transform.pred_cross is not baked into the base. Rebuilt on every main.system_predicted load, safe to drop.

Wolf-Rayet is fitted differently: on boxels at least 90% scanned (tier 1), falling back to 80% (tier 2), then to every scan (tier 3), taking the best tier with at least 5000 systems or else the largest. Commanders scan WR-bright boxels first, so a WR rate over all scans runs high.

*** A RATE OVER REPORTED BODIES IS A LOWER BOUND. *** An unreported body and an absent one are indistinguishable. And the scanned set is not random -- commanders pick interesting systems.';

COMMENT ON COLUMN transform.pred_rate.mass_code IS 'Boxel mass code, e to h.';
COMMENT ON COLUMN transform.pred_rate.band IS 'Band of distance from the galactic centre in the x/z plane: 0-10k, 10-20k, 20-30k, 30k+ ly.';
COMMENT ON COLUMN transform.pred_rate.n IS 'Scanned systems outside the cross in this cell -- the sample behind every rate except r_wr.';
COMMENT ON COLUMN transform.pred_rate.r_bh IS 'Share of those systems with a black hole row. Unrounded; rounded to 6 dp where it becomes p_bh.';
COMMENT ON COLUMN transform.pred_rate.r_wr IS 'Wolf-Rayet share on the tier chosen in wr_tier, NOT on all n systems.';
COMMENT ON COLUMN transform.pred_rate.wr_tier IS '1 = boxels >= 90% scanned, 2 = >= 80%, 3 = every scan. The basis r_wr was fitted on.';
COMMENT ON COLUMN transform.pred_rate.wr_n IS 'Systems behind r_wr.';
COMMENT ON COLUMN transform.pred_rate.r_neutron IS 'Share with a neutron star row.';
COMMENT ON COLUMN transform.pred_rate.r_wd IS 'Share with a white dwarf row.';
COMMENT ON COLUMN transform.pred_rate.r_herbig IS 'Share with a Herbig Ae/Be row.';
COMMENT ON COLUMN transform.pred_rate.r_otype IS 'Share with an O-type star row.';
COMMENT ON COLUMN transform.pred_rate.r_supergiant IS 'Share with a supergiant row.';

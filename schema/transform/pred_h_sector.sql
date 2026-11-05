CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.pred_h_sector;

CREATE TABLE transform.pred_h_sector (
    sector      VARCHAR NOT NULL PRIMARY KEY,
    p_wr_type   DOUBLE  NOT NULL,
    left_wr     DOUBLE  NOT NULL,
    left_bh     DOUBLE  NOT NULL,
    rate_wr     DOUBLE  NOT NULL,
    rate_bh     DOUBLE  NOT NULL,
    n_catalog   BIGINT  NOT NULL,
    n_unlisted  BIGINT  NOT NULL,
    alpha       DOUBLE  NOT NULL,
    eps         DOUBLE  NOT NULL
);

INSERT INTO transform.pred_h_sector
WITH evidence AS (
  SELECT c.*, t.*,
         least(c.found_wr, c.n_scanned) AS k_wr,
         least(c.found_bh, c.n_scanned) AS k_bh
  FROM transform.pred_h_count c
  JOIN transform.pred_h_type t USING (wr_layer, size_band)
),
typed AS (
  SELECT *,
         1.0 / (1.0 + exp(-least(greatest(
             tau * (k_wr * ln(wr_share_wr / wr_share_bh)
                    + (n_scanned - k_wr) * ln((1 - wr_share_wr) / (1 - wr_share_bh))
                    + k_bh * ln(bh_share_wr / bh_share_bh)
                    + (n_scanned - k_bh) * ln((1 - bh_share_wr) / (1 - bh_share_bh)))
             + ln(prior_wr / (1 - prior_wr)), -50), 50))) AS p_wr_type,
         greatest(n - n_scanned, 1) AS n_open
  FROM evidence
)
SELECT sector,
       round(p_wr_type, 6),
       round(p_wr_type * greatest(n * wr_rate_wr - found_wr, 0) + (1 - p_wr_type) * greatest(n * wr_rate_bh - found_wr, 0), 4),
       round(p_wr_type * greatest(n * bh_rate_wr - found_bh, 0) + (1 - p_wr_type) * greatest(n * bh_rate_bh - found_bh, 0), 4),
       round(p_wr_type * wr_rate_wr + (1 - p_wr_type) * wr_rate_bh, 6),
       round(p_wr_type * bh_rate_wr + (1 - p_wr_type) * bh_rate_bh, 6),
       least(n_catalog, n_open),
       n_open - least(n_catalog, n_open),
       alpha, eps
FROM typed;

COMMENT ON TABLE transform.pred_h_sector IS
'TRANSFORM: for each procedural sector with a known mass-h system, the chance it is Wolf-Rayet-rich and the Wolf-Rayets and black holes it still owes. transform.system_predicted shares what a sector owes among its unscanned mass-h names. Rebuilt on every main.system_predicted load, safe to drop.

The type starts from transform.pred_h_type.prior_wr for the sector''s layer and size and is updated by the binomial likelihood of its scanned shares, raised to tau. What a sector owes is its count times the type''s rate per system, less what is already found, never below 0, averaged over the two types by that chance.';

COMMENT ON COLUMN transform.pred_h_sector.sector IS 'Sector name, as transform.pred_pool.sector holds it.';
COMMENT ON COLUMN transform.pred_h_sector.p_wr_type IS 'Chance the sector is Wolf-Rayet-rich, 6 dp.';
COMMENT ON COLUMN transform.pred_h_sector.left_wr IS 'Wolf-Rayets the sector still owes, 4 dp.';
COMMENT ON COLUMN transform.pred_h_sector.left_bh IS 'Black holes the sector still owes, 4 dp.';
COMMENT ON COLUMN transform.pred_h_sector.rate_wr IS 'Wolf-Rayets per mass-h system for the sector, the two types'' rates averaged by p_wr_type, 6 dp; eps times this is the floor on a name''s p_wr.';
COMMENT ON COLUMN transform.pred_h_sector.rate_bh IS 'Black holes per mass-h system for the sector, 6 dp. See rate_wr.';
COMMENT ON COLUMN transform.pred_h_sector.n_catalog IS 'Unscanned catalogued mass-h names, at most the sector''s unscanned numbers.';
COMMENT ON COLUMN transform.pred_h_sector.n_unlisted IS 'Unscanned mass-h numbers no dump lists: the count less the scanned and the catalogued ones.';
COMMENT ON COLUMN transform.pred_h_sector.alpha IS 'Copied from transform.pred_h_type.alpha.';
COMMENT ON COLUMN transform.pred_h_sector.eps IS 'Copied from transform.pred_h_type.eps.';

CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.pred_h_type;

CREATE TABLE transform.pred_h_type (
    wr_layer     BOOLEAN NOT NULL,
    size_band    INTEGER NOT NULL,
    prior_wr     DOUBLE  NOT NULL,
    wr_rate_wr   DOUBLE  NOT NULL,
    wr_rate_bh   DOUBLE  NOT NULL,
    bh_rate_wr   DOUBLE  NOT NULL,
    bh_rate_bh   DOUBLE  NOT NULL,
    wr_share_wr  DOUBLE  NOT NULL,
    wr_share_bh  DOUBLE  NOT NULL,
    bh_share_wr  DOUBLE  NOT NULL,
    bh_share_bh  DOUBLE  NOT NULL,
    tau          DOUBLE  NOT NULL,
    alpha        DOUBLE  NOT NULL,
    eps          DOUBLE  NOT NULL,
    PRIMARY KEY (wr_layer, size_band)
);

INSERT INTO transform.pred_h_type
WITH well AS (
  SELECT *,
         (found_wr + found_bh) >= 0.1 * n_scanned
         AND (found_wr > 0.3 * n_scanned OR found_bh < 0.3 * n_scanned) AS wr_type
  FROM transform.pred_h_count
  WHERE n_scanned >= 30 AND cross_d > 1280
),
rates AS (
  SELECT sum(found_wr) FILTER (WHERE wr_type AND n_scanned >= 0.8 * n) / sum(n) FILTER (WHERE wr_type AND n_scanned >= 0.8 * n) AS wr_rate_wr,
         sum(found_wr) FILTER (WHERE NOT wr_type AND n_scanned >= 0.8 * n) / sum(n) FILTER (WHERE NOT wr_type AND n_scanned >= 0.8 * n) AS wr_rate_bh,
         sum(found_bh) FILTER (WHERE wr_type AND n_scanned >= 0.8 * n) / sum(n) FILTER (WHERE wr_type AND n_scanned >= 0.8 * n) AS bh_rate_wr,
         sum(found_bh) FILTER (WHERE NOT wr_type AND n_scanned >= 0.8 * n) / sum(n) FILTER (WHERE NOT wr_type AND n_scanned >= 0.8 * n) AS bh_rate_bh,
         sum(found_wr) FILTER (WHERE wr_type) / sum(n_scanned) FILTER (WHERE wr_type) AS wr_share_wr,
         sum(found_wr) FILTER (WHERE NOT wr_type) / sum(n_scanned) FILTER (WHERE NOT wr_type) AS wr_share_bh,
         sum(found_bh) FILTER (WHERE wr_type) / sum(n_scanned) FILTER (WHERE wr_type) AS bh_share_wr,
         sum(found_bh) FILTER (WHERE NOT wr_type) / sum(n_scanned) FILTER (WHERE NOT wr_type) AS bh_share_bh
  FROM well
),
cells AS (
  SELECT l.wr_layer, b.size_band
  FROM (VALUES (TRUE), (FALSE)) l(wr_layer), (VALUES (0), (1), (2)) b(size_band)
),
priors AS (
  SELECT c.wr_layer, c.size_band,
         (count(w.sector) FILTER (WHERE w.wr_type) + 1.0) / (count(w.sector) + 2.0) AS prior_wr
  FROM cells c
  LEFT JOIN well w ON w.wr_layer = c.wr_layer AND w.size_band = c.size_band
  GROUP BY 1, 2
)
SELECT p.wr_layer, p.size_band, round(p.prior_wr, 6),
       round(r.wr_rate_wr, 6), round(r.wr_rate_bh, 6), round(r.bh_rate_wr, 6), round(r.bh_rate_bh, 6),
       round(least(greatest(r.wr_share_wr, 0.0001), 0.9999), 6), round(least(greatest(r.wr_share_bh, 0.0001), 0.9999), 6),
       round(least(greatest(r.bh_share_wr, 0.0001), 0.9999), 6), round(least(greatest(r.bh_share_bh, 0.0001), 0.9999), 6),
       0.1, 10.0, 0.2
FROM priors p, rates r;

COMMENT ON TABLE transform.pred_h_type IS
'TRANSFORM: the two mass-h sector types and the prior of each, one row per (wr_layer, size_band). Rebuilt on every main.system_predicted load, safe to drop.

Within 10 kly of Sgr A* a mass-h sector is either Wolf-Rayet-rich or black-hole-rich, set per sector and not shared with its neighbours; the grid layer from y = -25 to +1,255 ly is almost entirely Wolf-Rayet-rich (MODEL.md). A sector counts as Wolf-Rayet-rich here when Wolf-Rayets and black holes are found in at least 10% of its scanned mass-h systems and either Wolf-Rayets in more than 30% or black holes in fewer than 30%. Types are fitted on the sectors with at least 30 scanned mass-h systems outside the cross (cross_d > 1280).

The rates per system are fitted on sectors scanned through (at least 80% of their mass-h systems), where the choice of what to scan no longer selects what is counted; the shares among scanned systems are fitted on every such sector and serve only to tell the two types apart.

tau, alpha and eps are fixed: tau 0.1, alpha 10, eps 0.2 were fitted on the mass-h predictions resolved after the 2026-10-21 snapshot, and the model was tested on the 2026-08-29 and 2026-09-25 snapshots and on 360 random galaxy-map plots (MODEL.md).';

COMMENT ON COLUMN transform.pred_h_type.wr_layer IS 'TRUE for the grid layer from y = -25 to +1,255 ly; see transform.pred_h_count.wr_layer.';
COMMENT ON COLUMN transform.pred_h_type.size_band IS 'Sector size band; see transform.pred_h_count.size_band.';
COMMENT ON COLUMN transform.pred_h_type.prior_wr IS 'Share of the fitted sectors in this layer and size band that are Wolf-Rayet-rich, with one pseudo-sector of each type: the chance a sector is Wolf-Rayet-rich before its own scans count.';
COMMENT ON COLUMN transform.pred_h_type.wr_rate_wr IS 'Wolf-Rayets per mass-h system in a Wolf-Rayet-rich sector.';
COMMENT ON COLUMN transform.pred_h_type.wr_rate_bh IS 'Wolf-Rayets per mass-h system in a black-hole-rich sector.';
COMMENT ON COLUMN transform.pred_h_type.bh_rate_wr IS 'Black holes per mass-h system in a Wolf-Rayet-rich sector.';
COMMENT ON COLUMN transform.pred_h_type.bh_rate_bh IS 'Black holes per mass-h system in a black-hole-rich sector.';
COMMENT ON COLUMN transform.pred_h_type.wr_share_wr IS 'Wolf-Rayets found per scanned mass-h system in a Wolf-Rayet-rich sector, clamped to 0.0001-0.9999. Selection-biased; used only for the likelihood of the type.';
COMMENT ON COLUMN transform.pred_h_type.wr_share_bh IS 'Wolf-Rayets found per scanned mass-h system in a black-hole-rich sector. See wr_share_wr.';
COMMENT ON COLUMN transform.pred_h_type.bh_share_wr IS 'Black holes found per scanned mass-h system in a Wolf-Rayet-rich sector. See wr_share_wr.';
COMMENT ON COLUMN transform.pred_h_type.bh_share_bh IS 'Black holes found per scanned mass-h system in a black-hole-rich sector. See wr_share_wr.';
COMMENT ON COLUMN transform.pred_h_type.tau IS 'Weight of a sector''s own scans against its prior, 0.1: the binomial likelihood of the scanned shares is raised to this power, because the scanned set is selection-biased and over-dispersed.';
COMMENT ON COLUMN transform.pred_h_type.alpha IS 'How many times a never-reported name''s share of the remaining budget a catalogued unscanned name takes, 10.';
COMMENT ON COLUMN transform.pred_h_type.eps IS 'Floor on a name''s chance as a share of its sector''s blended rate, 0.2, so a sector whose budget looks spent still keeps a chance.';

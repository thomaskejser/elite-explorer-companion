CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.pred_boxel_scan;

CREATE TABLE transform.pred_boxel_scan (
    sector_id   BIGINT  NOT NULL,
    cube_id     VARCHAR NOT NULL,
    mass_code   VARCHAR NOT NULL,
    sub_cube_id INTEGER,
    known       BIGINT  NOT NULL,
    scanned     BIGINT  NOT NULL,
    frac        DOUBLE  NOT NULL
);

INSERT INTO transform.pred_boxel_scan
SELECT k.sector_id, k.cube_id, k.mass_code, k.sub_cube_id,
       count(*),
       count(*) FILTER (WHERE l.n_scan_rows > 0 AND l.n_stars > 0),
       count(*) FILTER (WHERE l.n_scan_rows > 0 AND l.n_stars > 0)::DOUBLE / count(*)
FROM main.system_known k
LEFT JOIN transform.pred_labels l ON l.system_id = k.system_id
WHERE k.mass_code IN ('e', 'f', 'g', 'h') AND k.cube_id IS NOT NULL
GROUP BY 1, 2, 3, 4;

COMMENT ON TABLE transform.pred_boxel_scan IS
'TRANSFORM: scan completeness of every e/f/g/h boxel the model knows -- how many of its known systems have been SCANNED (per transform.pred_labels). Rebuilt on every main.system_predicted load, safe to drop.

It exists to fit the Wolf-Rayet rate on near-completely explored boxels only, because commanders scan WR-bright boxels first and a rate over all scans runs high. A boxel''s "known" systems are those some dump reports, not every system the generator placed, so frac is completeness OF THE KNOWN SET.';

COMMENT ON COLUMN transform.pred_boxel_scan.sector_id IS 'main.system_known.sector_id of the boxel. With cube_id, mass_code and sub_cube_id it identifies one boxel.';
COMMENT ON COLUMN transform.pred_boxel_scan.cube_id IS 'The AB-C letter triple of the procedural name.';
COMMENT ON COLUMN transform.pred_boxel_scan.mass_code IS 'Boxel mass code, e to h only.';
COMMENT ON COLUMN transform.pred_boxel_scan.sub_cube_id IS 'The number before the hyphen in the procedural name, 0 when absent. NULL only if system_known carries NULL.';
COMMENT ON COLUMN transform.pred_boxel_scan.known IS 'Systems main.system_known holds in this boxel. Not the number the generator placed.';
COMMENT ON COLUMN transform.pred_boxel_scan.scanned IS 'Of those, how many qualify as SCANNED in transform.pred_labels.';
COMMENT ON COLUMN transform.pred_boxel_scan.frac IS 'scanned / known. Unrounded -- used only for thresholds, never stored in main.';

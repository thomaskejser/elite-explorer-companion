CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.pred_labels;

CREATE TABLE transform.pred_labels (
    system_id      BIGINT  NOT NULL,
    has_bh         INTEGER NOT NULL,
    has_wr         INTEGER NOT NULL,
    has_neutron    INTEGER NOT NULL,
    has_wd         INTEGER NOT NULL,
    has_herbig     INTEGER NOT NULL,
    has_otype      INTEGER NOT NULL,
    has_supergiant INTEGER NOT NULL,
    n_stars        BIGINT  NOT NULL,
    n_scan_rows    BIGINT  NOT NULL,
    mass_code      VARCHAR,
    sector_id      BIGINT,
    cube_id        VARCHAR,
    sub_cube_id    INTEGER,
    cross_d        DOUBLE,
    plane_r        DOUBLE
);

COMMENT ON TABLE transform.pred_labels IS
'TRANSFORM: one row per system with typed body rows, flagging which rare targets main.system_body records there. The training labels for main.system_predicted; rebuilt on every load, safe to drop. No key constraint on purpose: ~75M rows, and a declared key would be maintained row by row.

BUILT IN 16 BUCKETS on abs((system_id >> 3) % 16) by etl/system_predicted/labels.sql, which also copies each system''s boxel and position from main.system_known, so transform.pred_boxel_scan, transform.pred_rate and transform.pred_cross read this table alone. One pass over every system_body row grouped by 77M systems and joined to 205M known systems needs more memory than the machine can spare beside the game; a sixteenth of it does not.

A system counts as SCANNED only when n_scan_rows > 0 AND n_stars > 0. Catalogue-only rows (edastro_rare, edastro_neutron, canonn_codex) are EXCLUDED from both counts: a catalogue listing one black hole says nothing about what else the system holds, so it must not count as an exploration.

*** A has_* OF 0 IS "NOT REPORTED", NOT "ABSENT". *** No source carries a DSS/mapped flag.';

COMMENT ON COLUMN transform.pred_labels.system_id IS 'main.system_known.system_id (the game''s id64).';
COMMENT ON COLUMN transform.pred_labels.has_bh IS '1 when a black hole (H) or supermassive black hole body row exists, from ANY source including catalogues.';
COMMENT ON COLUMN transform.pred_labels.has_wr IS '1 when a Wolf-Rayet (W, WN, WNC, WC, WO) body row exists.';
COMMENT ON COLUMN transform.pred_labels.has_neutron IS '1 when a neutron star body row exists.';
COMMENT ON COLUMN transform.pred_labels.has_wd IS '1 when any white dwarf (code D%) body row exists.';
COMMENT ON COLUMN transform.pred_labels.has_herbig IS '1 when a Herbig Ae/Be body row exists.';
COMMENT ON COLUMN transform.pred_labels.has_otype IS '1 when an O-type star body row exists.';
COMMENT ON COLUMN transform.pred_labels.has_supergiant IS '1 when a body whose code ends SuperGiant exists. Giants (K_OrangeGiant, M_RedGiant) are NOT included.';
COMMENT ON COLUMN transform.pred_labels.n_stars IS 'Star rows from SCAN sources only (catalogue-only sources excluded).';
COMMENT ON COLUMN transform.pred_labels.n_scan_rows IS 'Body rows of any type from SCAN sources only. Zero means the system is known only from catalogues.';
COMMENT ON COLUMN transform.pred_labels.mass_code IS 'main.system_known.mass_code; NULL for a system with body rows but no system_known row.';
COMMENT ON COLUMN transform.pred_labels.sector_id IS 'main.system_known.sector_id; with cube_id, mass_code and sub_cube_id it names the boxel, as transform.pred_boxel_scan.';
COMMENT ON COLUMN transform.pred_labels.cube_id IS 'main.system_known.cube_id.';
COMMENT ON COLUMN transform.pred_labels.sub_cube_id IS 'main.system_known.sub_cube_id.';
COMMENT ON COLUMN transform.pred_labels.cross_d IS 'least(|x|, |z|) in ly: distance to the nearer of the x = 0 and z = 0 planes, the axis of transform.pred_cross.';
COMMENT ON COLUMN transform.pred_labels.plane_r IS 'Distance in ly from Sagittarius A* (25.21875, -20.90625, 25899.96875) in the x/z plane, the axis of the plane_r bands.';

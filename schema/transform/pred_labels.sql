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
    n_scan_rows    BIGINT  NOT NULL
);

INSERT INTO transform.pred_labels
SELECT sb.system_id,
       max(CASE WHEN b.code IN ('H', 'SuperMassiveBlackHole')     THEN 1 ELSE 0 END),
       max(CASE WHEN b.code IN ('W', 'WN', 'WNC', 'WC', 'WO')     THEN 1 ELSE 0 END),
       max(CASE WHEN b.code = 'N'                                 THEN 1 ELSE 0 END),
       max(CASE WHEN b.code LIKE 'D%'                             THEN 1 ELSE 0 END),
       max(CASE WHEN b.code = 'AeBe'                              THEN 1 ELSE 0 END),
       max(CASE WHEN b.code = 'O'                                 THEN 1 ELSE 0 END),
       max(CASE WHEN b.code LIKE '%SuperGiant'                    THEN 1 ELSE 0 END),
       count(*) FILTER (WHERE b.type = 'star'
                          AND (sb.source NOT IN ('edastro_rare', 'edastro_neutron', 'canonn_codex')
                               OR sb.source IS NULL)),
       count(*) FILTER (WHERE sb.source NOT IN ('edastro_rare', 'edastro_neutron', 'canonn_codex')
                           OR sb.source IS NULL)
FROM main.system_body sb
JOIN main.body b ON b.body_id = sb.body_id
GROUP BY 1;

COMMENT ON TABLE transform.pred_labels IS
'TRANSFORM: one row per system with typed body rows, flagging which rare targets main.system_body records there. The training labels for main.system_predicted; rebuilt on every load, safe to drop. No key constraint on purpose: ~75M rows, and a declared key would be maintained row by row.

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

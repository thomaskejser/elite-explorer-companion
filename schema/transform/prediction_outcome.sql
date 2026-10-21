CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.prediction_outcome;

CREATE TABLE transform.prediction_outcome AS
WITH boxel AS (
    SELECT p.system, p.sector,
           regexp_extract(p.system, '^(.+) ([A-Z]{2}-[A-Z]) ([a-h])(?:([0-9]+)-)?([0-9]+)$',
                          ['sec', 'cube', 'mc', 'sub', 'idx']) AS n
    FROM transform.prediction_source p
    WHERE NOT p.is_catalog
      AND NOT EXISTS (SELECT 1 FROM main.prediction_outcome o WHERE o.system = p.system AND NOT o.is_catalog)
),
boxel_known AS (
    SELECT b.system, k.system_id
    FROM boxel b
    JOIN main.sector s ON s.sector = b.sector AND s.sector = b.n.sec
    JOIN main.system_known k
      ON k.sector_id = s.sector_id AND k.cube_id = b.n.cube AND k.mass_code = b.n.mc
     AND k.sub_cube_id = coalesce(nullif(b.n.sub, '')::INTEGER, 0)
     AND k.boxel_index = b.n.idx::INTEGER
    QUALIFY count(*) OVER (PARTITION BY b.system) = 1
),
fresh AS (
    SELECT p.* REPLACE (bk.system_id AS system_id), now() AS recorded_utc
    FROM transform.prediction_source p
    JOIN boxel_known bk ON bk.system = p.system
    WHERE NOT p.is_catalog
    UNION ALL
    SELECT p.*, now()
    FROM transform.prediction_source p
    WHERE p.is_catalog
      AND EXISTS (SELECT 1 FROM main.system_body b WHERE b.system_id = p.system_id)
      AND NOT EXISTS (SELECT 1 FROM main.prediction_outcome o WHERE o.system = p.system AND o.is_catalog)
),
keyed AS (
    SELECT system, is_catalog, system_id, sector, mass_code, x, y, z,
           p_bh, p_wr, p_neutron, p_wd, p_herbig, p_otype, p_supergiant, exp_bodies,
           predicted_in, recorded_utc
    FROM fresh
    UNION ALL
    SELECT system, is_catalog, system_id, sector, mass_code, x, y, z,
           p_bh, p_wr, p_neutron, p_wd, p_herbig, p_otype, p_supergiant, exp_bodies,
           predicted_in, recorded_utc
    FROM main.prediction_outcome
),
ids AS (SELECT DISTINCT system_id FROM keyed),
codes AS (
    SELECT sb.system_id, b.code,
           sb.source IN ('edastro_rare', 'edastro_neutron', 'canonn_codex') AS catalogue
    FROM main.system_body sb
    JOIN ids USING (system_id)
    LEFT JOIN main.body b ON b.body_id = sb.body_id
    UNION ALL
    SELECT k.system_id, b.code, NULL
    FROM main.system_known k
    JOIN ids USING (system_id)
    JOIN main.body b ON b.body_id = k.primary_star_body_id
),
actual AS (
    SELECT system_id,
           count(*) FILTER (WHERE NOT catalogue)::INTEGER AS surveyed_bodies,
           count(*) FILTER (WHERE catalogue)::INTEGER AS catalogue_bodies,
           bool_or(code IN ('H', 'SupermassiveBlackHole', 'SuperMassiveBlackHole')) AS found_bh,
           bool_or(code IN ('W', 'WN', 'WNC', 'WC', 'WO')) AS found_wr,
           bool_or(code = 'N') AS found_neutron,
           bool_or(code IN ('D', 'DA', 'DAB', 'DAO', 'DAV', 'DAZ', 'DB', 'DBV', 'DBZ', 'DC', 'DCV',
                            'DO', 'DOV', 'DQ', 'DX')) AS found_wd,
           bool_or(code = 'AeBe') AS found_herbig,
           bool_or(code = 'O') AS found_otype,
           bool_or(code IN ('A_BlueWhiteSuperGiant', 'B_BlueWhiteSuperGiant', 'F_WhiteSuperGiant',
                            'G_WhiteSuperGiant', 'M_RedSuperGiant')) AS found_supergiant
    FROM codes
    GROUP BY 1
)
SELECT q.*, k.first_seen,
       CASE WHEN coalesce(a.surveyed_bodies, 0) > 0 THEN 'survey'
            WHEN coalesce(a.catalogue_bodies, 0) > 0 THEN 'catalogue'
            ELSE 'known' END AS revealed_by,
       pb.code AS primary_code,
       coalesce(a.surveyed_bodies, 0) AS surveyed_bodies,
       coalesce(a.catalogue_bodies, 0) AS catalogue_bodies,
       coalesce(a.found_bh, false) AS found_bh,
       coalesce(a.found_wr, false) AS found_wr,
       coalesce(a.found_neutron, false) AS found_neutron,
       coalesce(a.found_wd, false) AS found_wd,
       coalesce(a.found_herbig, false) AS found_herbig,
       coalesce(a.found_otype, false) AS found_otype,
       coalesce(a.found_supergiant, false) AS found_supergiant
FROM keyed q
LEFT JOIN main.system_known k ON k.system_id = q.system_id
LEFT JOIN main.body pb ON pb.body_id = k.primary_star_body_id
LEFT JOIN actual a ON a.system_id = q.system_id;

COMMENT ON TABLE transform.prediction_outcome IS
'TRANSFORM: every row main.prediction_outcome should hold: the predictions newly resolved from transform.prediction_source plus the rows already recorded, each with its actuals recomputed from system_known and system_body. Rebuilt on every load, safe to drop.';

INSERT INTO transform.pred_labels
WITH labelled AS (
  SELECT sb.system_id,
         max(CASE WHEN b.code IN ('H', 'SuperMassiveBlackHole')     THEN 1 ELSE 0 END) AS has_bh,
         max(CASE WHEN b.code IN ('W', 'WN', 'WNC', 'WC', 'WO')     THEN 1 ELSE 0 END) AS has_wr,
         max(CASE WHEN b.code = 'N'                                 THEN 1 ELSE 0 END) AS has_neutron,
         max(CASE WHEN b.code LIKE 'D%'                             THEN 1 ELSE 0 END) AS has_wd,
         max(CASE WHEN b.code = 'AeBe'                              THEN 1 ELSE 0 END) AS has_herbig,
         max(CASE WHEN b.code = 'O'                                 THEN 1 ELSE 0 END) AS has_otype,
         max(CASE WHEN b.code LIKE '%SuperGiant'                    THEN 1 ELSE 0 END) AS has_supergiant,
         count(*) FILTER (WHERE b.type = 'star'
                            AND (sb.source NOT IN ('edastro_rare', 'edastro_neutron', 'canonn_codex')
                                 OR sb.source IS NULL)) AS n_stars,
         count(*) FILTER (WHERE sb.source NOT IN ('edastro_rare', 'edastro_neutron', 'canonn_codex')
                             OR sb.source IS NULL) AS n_scan_rows
  FROM main.system_body sb
  JOIN main.body b ON b.body_id = sb.body_id
  WHERE abs((sb.system_id >> 3) % ?) = ?
  GROUP BY 1
),
located AS (
  SELECT k.system_id, k.mass_code, k.sector_id, k.cube_id, k.sub_cube_id,
         least(abs(k.x), abs(k.z)) AS cross_d,
         sqrt(pow(k.x - 25.21875, 2) + pow(k.z - 25899.96875, 2)) AS plane_r
  FROM main.system_known k
  WHERE abs((k.system_id >> 3) % ?) = ?
)
SELECT l.system_id, l.has_bh, l.has_wr, l.has_neutron, l.has_wd, l.has_herbig, l.has_otype,
       l.has_supergiant, l.n_stars, l.n_scan_rows,
       k.mass_code, k.sector_id, k.cube_id, k.sub_cube_id, k.cross_d, k.plane_r
FROM labelled l
LEFT JOIN located k ON k.system_id = l.system_id;

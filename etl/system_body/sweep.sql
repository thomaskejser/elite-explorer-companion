UPDATE main.system_body SET is_primary = false
FROM (
    SELECT b.system_id, b.system_body, b.body_no,
           row_number() OVER (PARTITION BY b.system_id ORDER BY
               (b.system_body <> '') ASC,
               (b.source IN ('edastro_rare', 'edastro_neutron', 'canonn_codex')) ASC,
               (b.solar_masses IS NULL) ASC,
               (b.body_no < 0) ASC,
               b.body_no ASC,
               b.system_body ASC) AS rn
    FROM main.system_body b
    WHERE b.is_primary
      AND b.system_id IN (SELECT system_id FROM main.system_body WHERE is_primary
                          GROUP BY 1 HAVING count(*) > 1)
) d
WHERE main.system_body.system_id = d.system_id
  AND main.system_body.system_body = d.system_body
  AND main.system_body.body_no = d.body_no
  AND d.rn > 1
  AND main.system_body.is_primary;

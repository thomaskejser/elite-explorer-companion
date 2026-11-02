INSERT INTO transform.system_body
    (system_id, body_no, system_body, body_name, body_id, is_primary, discovered_time,
     solar_masses, earth_masses, is_terraformable, source)
WITH named AS (
    SELECT k.system_id,
           CASE WHEN k.sector_id = 0 OR sc.sector IS NULL THEN k.system_in_sector
                ELSE sc.sector || ' ' || k.system_in_sector END AS full_name
    FROM main.system_known k
    LEFT JOIN main.sector sc ON sc.sector_id = k.sector_id
    WHERE abs((k.system_id >> 3) % ?) = ?
),
raw AS (
    SELECT 1 AS pri, 'spansh' AS source, b.system_id64 AS system_id, b.name AS body_name,
           CAST(b.body_id AS INTEGER) AS body_no,
           lower(b.type) AS body_type, b.sub_type, coalesce(b.main_star, false) AS is_primary,
           b.solar_masses, b.earth_masses,
           b.terraforming_state = 'Terraformable' AS is_terraformable,
           CAST(NULL AS TIMESTAMP) AS discovered_at
    FROM staging.spansh_body b
    WHERE b.name IS NOT NULL AND abs((b.system_id64 >> 3) % ?) = ?

    UNION ALL
    SELECT 2, 'edsm', e.system_id64, e.name, e.body_no, lower(e.type), e.sub_type,
           coalesce(e.is_main_star, false), e.solar_masses, e.earth_masses,
           e.terraforming_state = 'Terraformable', NULL
    FROM staging.edsm_bodies7days e
    WHERE e.name IS NOT NULL AND abs((e.system_id64 >> 3) % ?) = ?

    UNION ALL
    SELECT 3, 'edastro', a.system_id64, a.name, a.body_no, 'planet', a.sub_type, false,
           NULL, a.earth_masses, a.terraforming_state = 'Terraformable', NULL
    FROM staging.edastro_planets7days a
    WHERE a.name IS NOT NULL AND abs((a.system_id64 >> 3) % ?) = ?

    UNION ALL
    SELECT 4, 'edastro_neutron', n.system_id64, n.body_name, NULL, 'star', 'Neutron Star',
           NULL, NULL, NULL, NULL, NULL
    FROM staging.edastro_neutron_stars n
    WHERE n.body_name IS NOT NULL AND abs((n.system_id64 >> 3) % ?) = ?

    UNION ALL
    SELECT 5, 'edastro_rare', r.system_id, r.body_name, NULL, 'star', r.star_type,
           r.is_main_star, NULL, NULL, NULL, r.discovered_at
    FROM transform.system_body_rare r
    WHERE abs((r.system_id >> 3) % ?) = ?
),
stripped AS (
    SELECT r.pri, r.source, r.system_id, r.body_name,
           CASE WHEN starts_with(r.body_name, n.full_name)
                THEN trim(substr(r.body_name, length(n.full_name) + 1))
                ELSE r.body_name END AS system_body,
           r.body_no,
           bo.body_id,
           CASE WHEN r.source = 'edastro_neutron' THEN r.body_name = n.full_name
                ELSE r.is_primary END AS is_primary,
           r.solar_masses, r.earth_masses, r.is_terraformable, r.discovered_at
    FROM raw r
    JOIN named n ON n.system_id = r.system_id
    LEFT JOIN main.body bo ON bo.body = r.sub_type AND bo.type = r.body_type
),
staged_no AS (
    SELECT system_id, system_body, min(body_no) AS body_no
    FROM stripped WHERE body_no >= 0
    GROUP BY 1, 2
),
held AS (
    SELECT t.system_id, t.system_body, min(t.body_no) AS body_no
    FROM main.system_body t
    WHERE abs((t.system_id >> 3) % ?) = ? AND t.body_no >= 0
    GROUP BY 1, 2
),
resolved AS (
    SELECT s.pri, s.source, s.system_id, s.body_name, s.system_body,
           CASE WHEN s.body_no >= 0 THEN s.body_no
                ELSE coalesce(sn.body_no, h.body_no, -1) END AS body_no,
           s.body_id, s.is_primary, s.solar_masses, s.earth_masses, s.is_terraformable
    FROM stripped s
    LEFT JOIN staged_no sn ON sn.system_id = s.system_id AND sn.system_body = s.system_body
    LEFT JOIN held h ON h.system_id = s.system_id AND h.system_body = s.system_body
),
discovered AS (
    SELECT system_id, system_body, min(discovered_at) AS discovered_time
    FROM stripped WHERE discovered_at IS NOT NULL
    GROUP BY 1, 2
),
picked AS (
    SELECT * FROM resolved
    QUALIFY row_number() OVER (PARTITION BY system_id, body_name, body_no ORDER BY pri) = 1
),
agg AS (
    SELECT system_id, system_body, body_no,
           min_by(body_name, pri)    AS body_name,
           max(body_id)              AS body_id,
           bool_or(is_primary)       AS is_primary,
           max(solar_masses)         AS solar_masses,
           max(earth_masses)         AS earth_masses,
           bool_or(is_terraformable) AS is_terraformable,
           min_by(source, pri)       AS source
    FROM picked
    GROUP BY 1, 2, 3
)
SELECT a.system_id, a.body_no, a.system_body, a.body_name, a.body_id, a.is_primary,
       d.discovered_time, a.solar_masses, a.earth_masses, a.is_terraformable, a.source
FROM agg a
LEFT JOIN discovered d ON d.system_id = a.system_id AND d.system_body = a.system_body;

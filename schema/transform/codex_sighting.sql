CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.codex_sighting;

CREATE TABLE transform.codex_sighting (
    codex          VARCHAR     NOT NULL,
    region_id      BIGINT      NOT NULL,
    sector_id      BIGINT      NOT NULL,
    entry          VARCHAR     NOT NULL,
    category       VARCHAR     NOT NULL,
    systems        INTEGER     NOT NULL CHECK (systems > 0),
    system_id      BIGINT      NOT NULL,
    system         VARCHAR     NOT NULL,
    x              DOUBLE,
    y              DOUBLE,
    z              DOUBLE,
    first_reported TIMESTAMPTZ,
    last_reported  TIMESTAMPTZ,
    PRIMARY KEY (codex, region_id, sector_id)
);

INSERT INTO transform.codex_sighting
WITH canonn AS (
    SELECT regexp_extract(lower(name), '^\$(.*)_name;$', 1) AS codex, min(hud_category) AS hud
    FROM staging.canonn_codex_event
    WHERE name IS NOT NULL
    GROUP BY 1
),
reports AS (
    SELECT e.type AS codex, min(e.name) AS name, r.region_id, k.sector_id, k.system_id,
           min(e.systemName) AS system, any_value(k.x) AS x, any_value(k.y) AS y, any_value(k.z) AS z,
           min(e.reportedOn)::TIMESTAMPTZ AS first_reported,
           max(e.reportedOn)::TIMESTAMPTZ AS last_reported
    FROM staging.edsm_codex_entry e
    JOIN main.region r ON r.region = e.region
    JOIN main.system_known k ON k.system_id = e.systemId64
    WHERE e.type IS NOT NULL
    GROUP BY e.type, r.region_id, k.sector_id, k.system_id
),
named AS (
    SELECT codex, min(name) AS name FROM reports GROUP BY 1
),
labelled AS (
    SELECT n.codex,
           CASE
               WHEN n.name NOT IN ('Non Terraformable', 'Terraformable', 'Standard Gas Giant', 'Green Gas Giant')
                   THEN n.name
               ELSE CASE WHEN n.codex LIKE 'codex_ent_green%' THEN 'Green '
                         WHEN n.codex LIKE 'codex_ent_trf%' THEN 'Terraformable '
                         ELSE '' END
                    || CASE regexp_replace(n.codex, '^codex_ent_(standard|trf|green)_', '')
                           WHEN 'ammonia_worlds' THEN 'ammonia world'
                           WHEN 'water_worlds' THEN 'water world'
                           WHEN 'high_metal_content_no_atmos' THEN 'high metal content world'
                           WHEN 'metal_rich_no_atmos' THEN 'metal-rich body'
                           WHEN 'rocky_no_atmos' THEN 'rocky body'
                           WHEN 'rocky_ice_no_atmos' THEN 'rocky ice world'
                           WHEN 'ice_no_atmos' THEN 'icy body'
                           WHEN 'ter_high_metal_content' THEN 'high metal content world with atmosphere'
                           WHEN 'ter_metal_rich' THEN 'metal-rich body with atmosphere'
                           WHEN 'ter_rocky' THEN 'rocky body with atmosphere'
                           WHEN 'ter_rocky_ice' THEN 'rocky ice world with atmosphere'
                           WHEN 'ter_ice' THEN 'icy body with atmosphere'
                           WHEN 'sudarsky_class_i' THEN 'class I gas giant'
                           WHEN 'sudarsky_class_ii' THEN 'class II gas giant'
                           WHEN 'sudarsky_class_iii' THEN 'class III gas giant'
                           WHEN 'sudarsky_class_iv' THEN 'class IV gas giant'
                           WHEN 'sudarsky_class_v' THEN 'class V gas giant'
                           WHEN 'helium' THEN 'helium gas giant'
                           WHEN 'helium_rich' THEN 'helium-rich gas giant'
                           WHEN 'giant_with_ammonia_life' THEN 'gas giant with ammonia-based life'
                           WHEN 'giant_with_water_life' THEN 'gas giant with water-based life'
                           WHEN 'water_giant' THEN 'water giant'
                           ELSE n.name END
           END AS entry,
           CASE
               WHEN c.hud IN ('Biology', 'Geology', 'Thargoid', 'Guardian') THEN c.hud
               WHEN c.hud IN ('Cloud', 'Anomaly') THEN 'Phenomena'
               WHEN c.hud = 'Tourist' THEN 'Planets'
               WHEN n.name LIKE 'Thargoid%' THEN 'Thargoid'
               WHEN n.codex LIKE 'codex_ent_standard%' OR n.codex LIKE 'codex_ent_trf%'
                 OR n.codex LIKE 'codex_ent_green%' OR n.codex = 'codex_ent_earth_likes' THEN 'Planets'
               ELSE 'Stars'
           END AS category
    FROM named n
    LEFT JOIN canonn c USING (codex)
)
SELECT r.codex, r.region_id, r.sector_id,
       upper(left(l.entry, 1)) || substr(l.entry, 2) AS entry,
       l.category,
       count(*)::INTEGER AS systems,
       arg_min(r.system_id, (r.first_reported, r.system_id)) AS system_id,
       arg_min(r.system, (r.first_reported, r.system_id)) AS system,
       arg_min(r.x, (r.first_reported, r.system_id)) AS x,
       arg_min(r.y, (r.first_reported, r.system_id)) AS y,
       arg_min(r.z, (r.first_reported, r.system_id)) AS z,
       min(r.first_reported) AS first_reported,
       max(r.last_reported) AS last_reported
FROM reports r
JOIN labelled l USING (codex)
GROUP BY r.codex, r.region_id, r.sector_id, l.entry, l.category;

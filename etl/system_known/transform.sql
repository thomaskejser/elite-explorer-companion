INSERT INTO transform.system_known_source
WITH src AS (
    SELECT 1                          AS pri,
           'spansh'                   AS source,
           s.system_id64              AS id64,
           clean_system_name(s.name)  AS name,
           s.x, s.y, s.z,
           s.declared_body_count      AS body_count,
           CAST(NULL AS BIGINT)       AS region_id,
           CAST(NULL AS VARCHAR)      AS main_star_type
    FROM staging.spansh_system s
    WHERE s.name IS NOT NULL AND s.x IS NOT NULL AND s.y IS NOT NULL AND s.z IS NOT NULL
      AND hash(system_id(s.system_id64, s.name)) % ? = ?

    UNION ALL
    SELECT 2, 'edsm', e.id64, clean_system_name(e.name),
           e.coords.x, e.coords.y, e.coords.z, NULL, NULL, NULL
    FROM staging.edsm_star_system e
    WHERE e.name IS NOT NULL AND e.coords.x IS NOT NULL
      AND e.coords.y IS NOT NULL AND e.coords.z IS NOT NULL
      AND hash(system_id(e.id64, e.name)) % ? = ?

    UNION ALL
    SELECT 3, 'edastro', a.id64, clean_system_name(a.name),
           a.coords.x, a.coords.y, a.coords.z, a.body_count, a.region, a.main_star_type
    FROM staging.edastro_star_system a
    WHERE a.name IS NOT NULL AND a.coords.x IS NOT NULL
      AND a.coords.y IS NOT NULL AND a.coords.z IS NOT NULL
      AND hash(system_id(a.id64, a.name)) % ? = ?
),
keyed AS (
    SELECT system_id(id64, name)                                     AS system_id,
           CAST(pri AS BIGINT) * 1000000000
             + CAST(hash(name) % 1000000000 AS BIGINT)                AS ord,
           source, name, x, y, z, body_count, region_id, main_star_type
    FROM src
    WHERE system_id(id64, name) IS NOT NULL
),
agg AS (
    SELECT system_id,
           min_by(name, ord)   AS name,
           min_by(source, ord) AS source,
           min_by(x, ord)      AS x,
           min_by(y, ord)      AS y,
           min_by(z, ord)      AS z,
           min_by(body_count, ord)     FILTER (WHERE body_count IS NOT NULL)     AS body_count,
           min_by(region_id, ord)      FILTER (WHERE region_id IS NOT NULL)      AS region_id,
           min_by(main_star_type, ord) FILTER (WHERE main_star_type IS NOT NULL) AS main_star_type
    FROM keyed
    GROUP BY system_id
),
split AS (
    SELECT a.*,
           regexp_matches(a.name, '^(.*) ([A-Z][A-Z]-[A-Z]) ([a-h])([0-9]+-)?([0-9]+)$') AS is_proc,
           nullif(regexp_extract(a.name, '^(.*) ([A-Z][A-Z]-[A-Z]) ([a-h])([0-9]+-)?([0-9]+)$', 1), '') AS sector_name
    FROM agg a
)
SELECT s.system_id,
       s.sector_name,
       s.is_proc,
       CASE WHEN s.is_proc THEN sc.sector_id ELSE 0 END AS sector_id,
       CASE WHEN s.is_proc
            THEN regexp_replace(s.name, '^(.*) ([A-Z][A-Z]-[A-Z]) ([a-h])([0-9]+-)?([0-9]+)$', '\2 \3\4\5')
            ELSE s.name END AS system_in_sector,
       CASE WHEN s.is_proc THEN nullif(regexp_extract(s.name, '^(.*) ([A-Z][A-Z]-[A-Z]) ([a-h])([0-9]+-)?([0-9]+)$', 2), '') END AS cube_id,
       CASE WHEN s.is_proc THEN nullif(regexp_extract(s.name, '^(.*) ([A-Z][A-Z]-[A-Z]) ([a-h])([0-9]+-)?([0-9]+)$', 3), '') END AS mass_code,
       CASE WHEN s.is_proc THEN CAST(coalesce(nullif(rtrim(
                regexp_extract(s.name, '^(.*) ([A-Z][A-Z]-[A-Z]) ([a-h])([0-9]+-)?([0-9]+)$', 4), '-'), ''), '0') AS INTEGER) END AS sub_cube_id,
       CASE WHEN s.is_proc THEN CAST(
                regexp_extract(s.name, '^(.*) ([A-Z][A-Z]-[A-Z]) ([a-h])([0-9]+-)?([0-9]+)$', 5) AS INTEGER) END AS boxel_index,
       coalesce(s.region_id, sc.region_id) AS region_id,
       coalesce(ps.primary_star_body_id, ba.body_id) AS primary_star_body_id,
       s.body_count,
       s.x, s.y, s.z,
       s.source
FROM split s
LEFT JOIN main.sector sc ON sc.sector = clean_sector_name(s.sector_name)
LEFT JOIN staging.primary_star ps
       ON ps.system_id64 = s.system_id AND hash(ps.system_id64) % ? = ?
LEFT JOIN main.body ba ON ba.type = 'star' AND ba.body = s.main_star_type;

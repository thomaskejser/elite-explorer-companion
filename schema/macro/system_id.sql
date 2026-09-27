CREATE OR REPLACE MACRO clean_system_name(s) AS (
    CASE WHEN s IS NULL THEN NULL
         ELSE nullif(trim(regexp_replace(s, '\s+', ' ', 'g')), '') END
);

CREATE OR REPLACE MACRO system_id_from_name(s) AS (
    CASE WHEN clean_system_name(s) IS NULL THEN NULL
         ELSE -(CAST(hash(clean_system_name(s)) % 4294967296 AS BIGINT) + 1) END
);

CREATE OR REPLACE MACRO system_id(id64, name) AS (
    CASE WHEN id64 IS NULL THEN system_id_from_name(name) ELSE id64 END
);

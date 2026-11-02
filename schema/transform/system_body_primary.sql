CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.system_body_primary;

CREATE TABLE transform.system_body_primary (
    system_id   BIGINT  NOT NULL PRIMARY KEY,
    system_body VARCHAR NOT NULL,
    body_no     INTEGER NOT NULL
);

INSERT INTO transform.system_body_primary
WITH prim AS (
    SELECT system_id, system_body, body_no, body_name
    FROM transform.system_body
    WHERE is_primary
),
ambiguous AS (
    SELECT system_id FROM prim GROUP BY 1 HAVING count(DISTINCT (system_body, body_no)) > 1
),
ranked AS (
    SELECT p.system_id, p.system_body, p.body_no,
           row_number() OVER (
               PARTITION BY p.system_id ORDER BY
                   (b.dist_to_arrival_ls IS NULL),
                   b.dist_to_arrival_ls NULLS LAST,
                   (b.sub_type IS NULL OR coalesce(b.solar_masses, 0) <= 0),
                   (p.body_no < 0),
                   p.body_no,
                   p.system_body) AS rn
    FROM prim p
    JOIN ambiguous a USING (system_id)
    LEFT JOIN staging.spansh_body b
           ON b.system_id64 = p.system_id AND b.name = p.body_name
          AND (p.body_no < 0 OR b.body_id = p.body_no)
)
SELECT system_id, system_body, body_no FROM ranked WHERE rn = 1;

COMMENT ON TABLE transform.system_body_primary IS
'TRANSFORM: one winning arrival star for every staged system whose feeds name more than one. Rebuilt after every system_body merge from transform.system_body -- derived, never edited, safe to drop.

The winner is the body nearest the arrival point in the Spansh dump, then one with a real stellar mass, then the lowest known body_no, then the designation. A system the staged window does not touch is not here, and the global sweep in etl/system_body/sweep.sql settles those.';

COMMENT ON COLUMN transform.system_body_primary.system_id IS
'The system with an ambiguous primary. PRIMARY KEY: exactly one winner each.';

COMMENT ON COLUMN transform.system_body_primary.system_body IS
'The designation of the body that keeps is_primary; every other primary row of the system is demoted.';

COMMENT ON COLUMN transform.system_body_primary.body_no IS
'The winning body''s index within its system; with system_body it names exactly one main.system_body row. -1 when the winner''s index is unknown.';

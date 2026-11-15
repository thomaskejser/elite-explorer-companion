CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.body;

CREATE TABLE transform.body (
    body_id                INTEGER NOT NULL UNIQUE,
    type                   VARCHAR NOT NULL CHECK (type IN ('star', 'planet')),
    body                   VARCHAR NOT NULL CHECK (trim(body) <> ''),
    is_terraform_candidate BOOLEAN NOT NULL,
    code                   VARCHAR,
    cr_value               DOUBLE,
    cr_value_terraformable DOUBLE,
    value_formula          VARCHAR,
    PRIMARY KEY (type, body)
);

INSERT INTO transform.body
WITH matched AS (
    SELECT c.*, m.body_id AS have_id
    FROM staging.body_curated c
    LEFT JOIN main.body m ON m.type = c.type AND m.body = c.body
),
fresh AS (
    SELECT *,
           body_id IS NOT NULL
             AND NOT EXISTS (SELECT 1 FROM main.body m WHERE m.body_id = matched.body_id)
             AND count(*) OVER (PARTITION BY body_id) = 1 AS keep_id
    FROM matched
    WHERE have_id IS NULL
),
ceiling AS (
    SELECT greatest((SELECT coalesce(max(body_id), 0) FROM main.body),
                    (SELECT coalesce(max(body_id), 0) FROM fresh WHERE keep_id)) AS top
),
assigned AS (
    SELECT type, body, have_id AS body_id FROM matched WHERE have_id IS NOT NULL
    UNION ALL
    SELECT type, body,
           CASE WHEN keep_id THEN body_id
                ELSE (SELECT top FROM ceiling)
                     + CAST(row_number() OVER (PARTITION BY keep_id ORDER BY type, body) AS INTEGER)
           END
    FROM fresh
)
SELECT a.body_id, c.type, c.body, c.is_terraform_candidate, c.code,
       c.cr_value, c.cr_value_terraformable, c.value_formula
FROM staging.body_curated c
JOIN assigned a ON a.type = c.type AND a.body = c.body;

COMMENT ON TABLE transform.body IS
'TRANSFORM: staging.body_curated shaped exactly as main.body merges it. Rebuilt on every load -- derived, never edited, safe to drop.

Its constraints are the input validation: (type, body) is the PRIMARY KEY, so a duplicated natural key in the hand-edited parquet fails HERE rather than reaching main; body_id is UNIQUE, so an id collision fails too.

It carries the curated attributes only. main.body''s observed/bodies statistics are not from the file: etl/body/load.sql inserts a new type with 0 and FALSE, and etl/body/census.sql recounts every type from staging.spansh_galaxy_body when the full catalogue is staged.

body_id is RESOLVED, not copied: an existing (type, body) keeps main.body''s id; a new one takes the parquet''s id when no body holds it and no other new row proposes it, else the next id above everything held. Nothing is renumbered.';

COMMENT ON COLUMN transform.body.body_id IS
'main.body''s id for an existing type, else the resolved id for a new one (see the table comment). UNIQUE, enforced above.';

COMMENT ON COLUMN transform.body.type IS
'''star'' or ''planet'', from the parquet. Half the PRIMARY KEY.';

COMMENT ON COLUMN transform.body.body IS
'Sub-type name as the dumps spell it, from the parquet. Half the PRIMARY KEY.';

COMMENT ON COLUMN transform.body.is_terraform_candidate IS
'From the parquet, as curated.';

COMMENT ON COLUMN transform.body.code IS
'From the parquet, as curated. NULL for planets.';

COMMENT ON COLUMN transform.body.cr_value IS
'From the parquet, as curated.';

COMMENT ON COLUMN transform.body.cr_value_terraformable IS
'From the parquet, as curated.';

COMMENT ON COLUMN transform.body.value_formula IS
'From the parquet, as curated.';

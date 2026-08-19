-- body: reference dimension of body TYPES. Load order tier 1 (no dependencies).
-- Comment text lives in schema/body_comment.sql -- apply both.
CREATE TABLE IF NOT EXISTS body (
    body_id                INTEGER NOT NULL PRIMARY KEY,
    type                   VARCHAR NOT NULL,
    body                   VARCHAR NOT NULL,
    is_terraform_candidate BOOLEAN NOT NULL,
    code                   VARCHAR,
    observed               BOOLEAN NOT NULL,
    bodies                 BIGINT  NOT NULL,
    cr_value               DOUBLE,
    cr_value_terraformable DOUBLE,
    value_formula          VARCHAR
);

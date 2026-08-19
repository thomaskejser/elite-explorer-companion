-- body_type_census: galaxy-wide body census by type/sub_type. Load order tier 1.
-- Derived from spansh_body; standalone, no foreign keys.
CREATE TABLE IF NOT EXISTS body_type_census (
    type              VARCHAR NOT NULL,
    sub_type          VARCHAR NOT NULL,
    bodies            BIGINT  NOT NULL,
    share_all_pct     DOUBLE  NOT NULL,
    share_of_type_pct DOUBLE  NOT NULL,
    PRIMARY KEY (type, sub_type)
);

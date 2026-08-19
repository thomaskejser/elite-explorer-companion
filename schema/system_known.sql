-- system_known: every system we know exists. Load order tier 2
-- (needs sector, region, body, poi).
CREATE TABLE IF NOT EXISTS system_known (
    system_id   BIGINT  NOT NULL PRIMARY KEY,
    sector_id   BIGINT  NOT NULL,
    "system"    VARCHAR NOT NULL,
    cube_id     VARCHAR,
    mass_code   VARCHAR,
    sub_cube_id INTEGER,
    boxel_index INTEGER,
    region_id   BIGINT,
    primary_star_body_id INTEGER,
    body_count  INTEGER,
    x           DOUBLE,
    y           DOUBLE,
    z           DOUBLE,
    id_poi      INTEGER,
    -- NO UNIQUE constraint: 96 id64 values map to two rows each, the same system
    -- recorded under two name spellings. A real defect this column exposed, not id64
    -- reuse -- fix the duplicates, then add the key.
    id64        BIGINT,
    UNIQUE ("sector_id", "system"),
    FOREIGN KEY (sector_id) REFERENCES sector (sector_id),
    FOREIGN KEY (region_id) REFERENCES region (region_id),
    FOREIGN KEY (primary_star_body_id) REFERENCES body (body_id),
    FOREIGN KEY (id_poi) REFERENCES poi (poi_id)
);

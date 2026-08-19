-- poi: the point-of-interest dimension. Load order tier 1.
-- Target of system_known.id_poi and system_body.id_poi.
CREATE TABLE IF NOT EXISTS poi (
    poi_id        INTEGER NOT NULL PRIMARY KEY,
    poi           VARCHAR NOT NULL,
    poi_class     VARCHAR NOT NULL,
    poi_family    VARCHAR,
    needs_landing BOOLEAN NOT NULL,
    sources       VARCHAR,
    systems       INTEGER,
    bodies        INTEGER
);

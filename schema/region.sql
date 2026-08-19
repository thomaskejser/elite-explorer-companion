-- region: the 42 hand-drawn galactic regions. Load order tier 1.
-- region_id is the GAME's id, not ours: never allocated, always taken as given.
CREATE TABLE IF NOT EXISTS region (
    region_id BIGINT  NOT NULL PRIMARY KEY,
    region    VARCHAR NOT NULL UNIQUE
);

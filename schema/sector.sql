-- sector: one row per unique sector with a rough bounding ball. Load order tier 1.
-- GOTCHA: is_crafted is TRUE for 424 REAL named sectors, not just the sector_id=0
-- sentinel. Only sector_id=0 means a system's name stands alone. See ETL.md.
CREATE TABLE IF NOT EXISTS sector (
    sector_id  BIGINT  NOT NULL PRIMARY KEY,
    sector     VARCHAR NOT NULL UNIQUE,
    x          DOUBLE  NOT NULL,
    y          DOUBLE  NOT NULL,
    z          DOUBLE  NOT NULL,
    radius     DOUBLE  NOT NULL,
    is_crafted BOOLEAN NOT NULL,
    -- LAST, because build_sector.py adds it with ensure_columns() rather than in its
    -- CREATE, and ALTER TABLE ADD COLUMN can only append. Nullable: one sector of
    -- 12,065 has no region. All 12,064 populated values resolve, so unlike the old
    -- database this declares the foreign key.
    region_id  BIGINT,
    FOREIGN KEY (region_id) REFERENCES region (region_id)
);

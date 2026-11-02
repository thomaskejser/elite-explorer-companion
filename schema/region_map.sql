CREATE TABLE IF NOT EXISTS region_map (
    z_row     INTEGER NOT NULL,
    x_start   INTEGER NOT NULL,
    length    INTEGER NOT NULL,
    region_id BIGINT  NOT NULL,
    PRIMARY KEY (z_row, x_start)
);

COMMENT ON TABLE region_map IS
'The galactic REGION GRID: which region each cell of the galactic plane belongs to, as horizontal runs. From klightspeed''s EliteDangerousRegionMap (MIT), staged as staging.klightspeed_region_map by etl/region_map/refresh.py. 2,048 x 2,048 cells; cell (x_cell, z_row) covers galactic x from -49985 + x_cell * 4096/83 and z from -24105 + z_row * 4096/83, about 49.35 ly a side, and ignores y. Cells outside every region have no run.

What it is for: drawing the regions and finding the region under a point on a map (the overlay''s Map tab). It is a published approximation of Frontier''s hand-drawn regions, so a system''s region is still main.system_known.region_id; do not re-derive that from here.

*** THIS TABLE DELETES. *** A run absent from the source is wrong geometry, not a retired key: left in place it would overlap the runs that replaced it and corrupt the grid, so the loader deletes it (ETL.md, the deleting exceptions).';

COMMENT ON COLUMN region_map.z_row IS
'Grid row, 0-based, along galactic z: z = -24105 + z_row * 4096/83. Half the key.';

COMMENT ON COLUMN region_map.x_start IS
'First cell of the run along galactic x: x = -49985 + x_start * 4096/83. Half the key.';

COMMENT ON COLUMN region_map.length IS
'Cells in the run; the run covers x_start .. x_start + length - 1.';

COMMENT ON COLUMN region_map.region_id IS
'References region.region_id. Unenforced, like every reference here; common.db.check_references counts dangling rows.';

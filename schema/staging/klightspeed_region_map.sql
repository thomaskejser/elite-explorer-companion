CREATE TABLE IF NOT EXISTS staging.klightspeed_region_map (
    z_row   INTEGER NOT NULL,
    run_no  INTEGER NOT NULL,
    length  INTEGER NOT NULL,
    region  VARCHAR
);

COMMENT ON TABLE staging.klightspeed_region_map IS
'RAW SOURCE (not a work table -- never drop or rebuild): the galactic region grid from https://github.com/klightspeed/EliteDangerousRegionMap (RegionMapData.json, MIT licence), downloaded by etl/region_map/stage.py. One row per run of the run-length encoding, exactly as published: 2,048 rows of the galactic plane, each a list of (length, region) runs summing to 2,048 cells. It is the region lookup EDDiscovery and EDMC use; Frontier publishes no region boundaries.';

COMMENT ON COLUMN staging.klightspeed_region_map.z_row IS
'Grid row, 0-based. Row r covers galactic z from -24105 + r * 4096/83 ly; see main.region_map for the transform.';

COMMENT ON COLUMN staging.klightspeed_region_map.run_no IS
'1-based position of the run within its row. Runs are contiguous and in x order, so a run''s first cell is the sum of the lengths before it.';

COMMENT ON COLUMN staging.klightspeed_region_map.length IS
'Cells in the run.';

COMMENT ON COLUMN staging.klightspeed_region_map.region IS
'The region name as the source spells it, NULL outside every region. Matches main.region.region except that the source writes ''Formidine Rift'' where the codex writes ''The Formidine Rift''.';

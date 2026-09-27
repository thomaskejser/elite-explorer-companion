CREATE TABLE IF NOT EXISTS staging.edastro_sector (
    sector             VARCHAR,
    systems            BIGINT,
    avg_x              DOUBLE,
    avg_y              DOUBLE,
    avg_z              DOUBLE,
    min_x              DOUBLE,
    min_y              DOUBLE,
    min_z              DOUBLE,
    max_x              DOUBLE,
    max_y              DOUBLE,
    max_z              DOUBLE,
    map_sector_x       BIGINT,
    map_sector_y       BIGINT,
    first_encountered  TIMESTAMP,
    id64_x             BIGINT,
    id64_y             BIGINT,
    id64_z             BIGINT
);

COMMENT ON TABLE staging.edastro_sector IS
'RAW SOURCE (not a work table -- never drop or rebuild): EDAstro''s sector list, downloaded whole from https://edastro.com/mapcharts/files/sector-list.csv by etl/sector/stage.py. FULL, and refreshed roughly daily.

*** NOT A CATALOGUE OF EVERY SECTOR. *** One row per sector EDAstro has seen a system in, so it is an OBSERVED set exactly like the one this project used to infer from system names -- the `systems` and `first_encountered` columns are what give it away. 12,083 rows covering 99.3M systems, against the 200.7M in system_known, so it is not even the larger observation. Ten sectors here are absent from main.sector and twenty-six of ours are absent from it.

What it adds over inference is the id64 grid cell, which nothing else here carries.';

COMMENT ON COLUMN staging.edastro_sector.sector IS
'Sector name as EDAstro spells it. Pass it through clean_sector_name() before matching: this feed and ours share one casing defect (''Blue planetary Sector'') and nothing guarantees the whitespace.';

COMMENT ON COLUMN staging.edastro_sector.systems IS
'How many systems EDAstro knows in this sector. A COVERAGE measure of their database, not a property of the sector -- the galaxy''s real count is unknown and far larger.';

COMMENT ON COLUMN staging.edastro_sector.avg_x IS
'MEAN x over known systems, so it follows where commanders have flown. main.sector.x is the bounding-box MIDPOINT instead, which is the definition this project has always used -- do not mix them.';

COMMENT ON COLUMN staging.edastro_sector.avg_y IS 'Mean y over known systems. See avg_x: not the midpoint.';
COMMENT ON COLUMN staging.edastro_sector.avg_z IS 'Mean z over known systems. See avg_x: not the midpoint.';

COMMENT ON COLUMN staging.edastro_sector.min_x IS
'Lowest x of any known system in the sector. With max_x it gives the bounding box main.sector.x and .radius are derived from. A FLOOR on the sector''s extent, never its true size: an unvisited corner simply is not in it.';

COMMENT ON COLUMN staging.edastro_sector.min_y IS 'Lowest y of any known system. See min_x.';
COMMENT ON COLUMN staging.edastro_sector.min_z IS 'Lowest z of any known system. See min_x.';
COMMENT ON COLUMN staging.edastro_sector.max_x IS 'Highest x of any known system. See min_x.';
COMMENT ON COLUMN staging.edastro_sector.max_y IS 'Highest y of any known system. See min_x.';
COMMENT ON COLUMN staging.edastro_sector.max_z IS 'Highest z of any known system. See min_x.';

COMMENT ON COLUMN staging.edastro_sector.map_sector_x IS
'EDAstro''s own 2D map-tile column, for their charts. NOT the id64 grid -- use id64_x for that.';

COMMENT ON COLUMN staging.edastro_sector.map_sector_y IS 'EDAstro''s 2D map-tile row. See map_sector_x.';

COMMENT ON COLUMN staging.edastro_sector.first_encountered IS
'When EDAstro first recorded a system here. A fact about REPORTING history, not about the sector.';

COMMENT ON COLUMN staging.edastro_sector.id64_x IS
'The sector''s x cell in the game''s own 1280 ly grid, the same field id64 packs -- equal to floor((min_x + 49985) / 1280) on 11,569 of 12,083 rows. Together with id64_y and id64_z it is UNIQUE across all 11,649 rows that have one, so it is a genuine game-derived sector address.

*** NULL ON 434 ROWS, AND THE NULL IS INFORMATION. *** Those are the HAND-AUTHORED sectors -- Col 359 Sector, NGC 2546 Sector, Bleia1..5, ICZ -- which are named overlays on the procedural grid rather than cells of it, so they have no address to carry. That is a better is_crafted test than matching the name, and it is what main.sector.is_crafted now uses.';

COMMENT ON COLUMN staging.edastro_sector.id64_y IS 'The sector''s y cell in the id64 grid. See id64_x, including what a NULL means.';
COMMENT ON COLUMN staging.edastro_sector.id64_z IS 'The sector''s z cell in the id64 grid. See id64_x, including what a NULL means.';

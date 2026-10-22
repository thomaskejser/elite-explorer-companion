CREATE TABLE IF NOT EXISTS galaxy_density (
    cell_x   INTEGER NOT NULL,
    cell_z   INTEGER NOT NULL,
    systems  BIGINT  NOT NULL,
    PRIMARY KEY (cell_x, cell_z)
);

COMMENT ON TABLE galaxy_density IS
'MIRROR-ONLY, DERIVED: count of main.system_known rows per cell of a 1,024 x 1,024 grid on the galactic plane, ignoring y. Cell (cell_x, cell_z) covers x from -49985 + cell_x * 8192/83 and z from -24105 + cell_z * 8192/83, about 98.7 ly a side: two region_map cells per side. It draws the galaxy behind the overlay''s Map tab. It measures where commanders have reported systems, NOT the galaxy''s real star density -- the unexplored far side is dark because nobody has been there. Empty cells have no row. Rebuilt whole by etl/refresh_current.py.';

COMMENT ON COLUMN galaxy_density.cell_x IS 'Grid column along galactic x, 0-based. Half the key.';
COMMENT ON COLUMN galaxy_density.cell_z IS 'Grid row along galactic z, 0-based. Half the key.';
COMMENT ON COLUMN galaxy_density.systems IS 'Known systems in the cell.';

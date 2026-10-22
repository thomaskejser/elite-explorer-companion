CREATE TABLE IF NOT EXISTS sector_known (
    sector_id   BIGINT  NOT NULL PRIMARY KEY,
    systems     BIGINT  NOT NULL
);

COMMENT ON TABLE sector_known IS
'MIRROR-ONLY, DERIVED: count of main.system_known rows per sector_id, so the overlay can show how many systems a sector already has on record without reading the 200M-row table. sector_id 0 is the crafted sentinel and counts every hand-named system together. Rebuilt whole by etl/refresh_current.py.';

COMMENT ON COLUMN sector_known.sector_id IS 'References sector.sector_id.';
COMMENT ON COLUMN sector_known.systems IS 'Systems in main.system_known with this sector_id.';

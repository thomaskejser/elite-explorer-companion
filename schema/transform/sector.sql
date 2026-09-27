CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.sector;

CREATE TABLE transform.sector (
    sector_id  BIGINT  NOT NULL PRIMARY KEY,
    sector     VARCHAR NOT NULL UNIQUE CHECK (trim(sector) <> ''),
    x          DOUBLE  NOT NULL,
    y          DOUBLE  NOT NULL,
    z          DOUBLE  NOT NULL,
    radius     DOUBLE  NOT NULL CHECK (radius >= 0),
    is_crafted BOOLEAN NOT NULL
);

INSERT INTO transform.sector (sector_id, sector, x, y, z, radius, is_crafted)
WITH cell AS (
    SELECT *, (id64_x = 0 AND id64_y = 0 AND id64_z = 0) AS is_origin
    FROM staging.edastro_sector
)
SELECT sector_id(clean_sector_name(sector),
                 any_value(CASE WHEN NOT is_origin THEN id64_x END),
                 any_value(CASE WHEN NOT is_origin THEN id64_y END),
                 any_value(CASE WHEN NOT is_origin THEN id64_z END)),
       clean_sector_name(sector),
       round((min(min_x) + max(max_x)) / 2, 6),
       round((min(min_y) + max(max_y)) / 2, 6),
       round((min(min_z) + max(max_z)) / 2, 6),
       round(((max(max_x) - min(min_x))
            + (max(max_y) - min(min_y))
            + (max(max_z) - min(min_z))) / 2, 6),
       bool_and(id64_x IS NULL OR is_origin)
FROM cell
WHERE sector IS NOT NULL AND trim(sector) <> ''
  AND min_x IS NOT NULL AND min_y IS NOT NULL AND min_z IS NOT NULL
  AND max_x IS NOT NULL AND max_y IS NOT NULL AND max_z IS NOT NULL
GROUP BY clean_sector_name(sector);

COMMENT ON TABLE transform.sector IS
'TRANSFORM: staging.edastro_sector reshaped to exactly what main.sector merges. Rebuilt on every load -- derived, never edited.

Names go through clean_sector_name() here, which is what makes the join to main.sector safe.

sector_id is DERIVED, not allocated -- see the column comment. Nothing here reads main.sector, so this table can be built against an empty database.

The sentinel sector_id = 0 is NOT produced here. It is not a sector and no feed reports it; main.sector keeps it and orphans.sql excludes it.';

COMMENT ON COLUMN transform.sector.sector_id IS
'THE GAME''S OWN SECTOR ADDRESS, not a sequence we allocate. Computed by the sector_id() macro: for a procedural sector it packs the id64 grid cell as x + 128y + 16384z, giving 35,968..1,151,014 and decoding straight back with sid%128, (sid//128)%128, sid//16384.

*** HAND-AUTHORED SECTORS GET A NEGATIVE ID. *** They are named overlays on the grid and have no cell, so there is nothing to pack; sector_id_from_name() hashes the cleaned name to 32 bits and negates it, which cannot collide with a packed cell because the sign differs. Verified across all 12,083 rows: 12,083 distinct ids, none zero, no procedural id outside the 21-bit space and no hand-authored id positive.

Two consequences. The sign of this column IS the is_crafted flag. And an id is only as stable as hash(), which DuckDB does not promise across versions -- existing rows are safe because the merge matches on the NAME, but a sector first seen after a hash change would get a different id than it would have before.';

COMMENT ON COLUMN transform.sector.sector IS
'Cleaned sector name, the natural key the merge matches on. UNIQUE is enforced above: two source rows cleaning to one name would otherwise merge two sectors into one, silently.';

COMMENT ON COLUMN transform.sector.x IS
'Bounding-box MIDPOINT of known systems, (min + max) / 2 -- deliberately not EDAstro''s avg_x, which is a mean over reported systems and therefore follows commander traffic.';

COMMENT ON COLUMN transform.sector.y IS 'Bounding-box midpoint. See x.';
COMMENT ON COLUMN transform.sector.z IS 'Bounding-box midpoint. See x.';

COMMENT ON COLUMN transform.sector.radius IS
'TAXICAB half-extent of the bounding box: half the sum of the three side lengths, which is the taxicab distance from the midpoint to a corner. A FLOOR on the sector''s size, since the box only covers systems somebody has reported.';

COMMENT ON COLUMN transform.sector.is_crafted IS
'TRUE when the sector has no id64 grid cell, which is what makes it hand-authored rather than procedural. Strictly better than matching the name: it also catches Bleia1..5, Bovomit, Dryman, Froadik, Hyponia, ICZ, Praei1, Praei3 and Sidgoir, none of which end in Sector or Dark Region.';

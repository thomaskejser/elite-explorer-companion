CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.pred_boxel_first;

CREATE TABLE transform.pred_boxel_first (
    sector_id   BIGINT  NOT NULL PRIMARY KEY,
    cube_id     VARCHAR NOT NULL,
    mass_code   VARCHAR NOT NULL,
    sub_cube_id INTEGER NOT NULL,
    sector      VARCHAR NOT NULL,
    boxel_index BIGINT  NOT NULL,
    x           DOUBLE  NOT NULL,
    y           DOUBLE  NOT NULL,
    z           DOUBLE  NOT NULL
);

INSERT INTO transform.pred_boxel_first
WITH has_h0 AS (
  SELECT DISTINCT sector_id
  FROM main.system_known
  WHERE mass_code = 'h' AND cube_id = 'AA-A' AND sub_cube_id = 0 AND boxel_index = 0
)
SELECT s.sector_id, 'AA-A', 'h', 0, s.sector, 0,
       -49985 + (s.sector_id % 128) * 1280 + 640,
       -40985 + ((s.sector_id // 128) % 128) * 1280 + 640,
       -24105 + (s.sector_id // 16384) * 1280 + 640
FROM main.sector s
WHERE s.sector_id > 0
  AND s.sector_id NOT IN (SELECT sector_id FROM has_h0);

COMMENT ON TABLE transform.pred_boxel_first IS
'TRANSFORM: the first system of every grid sector''s h boxel, <sector> AA-A h0, where main.system_known does not hold it -- the boxel-predicted rows the gap enumeration cannot reach, because a gap needs two known indices to sit between and an empty or one-system boxel has none. Rebuilt on every main.system_predicted load, safe to drop.

An h boxel is the whole 1280 ly sector, so every grid sector has exactly one and its first system can only be called AA-A h0.

*** A GUESS THAT THE SYSTEM EXISTS, NOT AN INFERENCE FROM A GAP. *** An h boxel can be empty: a sector with 50,000 or more known systems still has no known h system about one time in ten, and far from the plane most sectors have none. The commander marks a probe that does not exist as wrong, which removes it.

Grid sectors only (sector_id > 0): a hand-authored sector has no grid cell, so its boxel letters are not fixed by position.';

COMMENT ON COLUMN transform.pred_boxel_first.sector_id IS 'main.sector.sector_id, the grid cell cx + 128 cy + 16384 cz.';
COMMENT ON COLUMN transform.pred_boxel_first.cube_id IS 'Always AA-A: the h boxel is the whole sector, so its letters are always the first.';
COMMENT ON COLUMN transform.pred_boxel_first.mass_code IS 'Always h.';
COMMENT ON COLUMN transform.pred_boxel_first.sub_cube_id IS 'Always 0: an h name carries no number before a hyphen.';
COMMENT ON COLUMN transform.pred_boxel_first.sector IS 'The sector NAME from main.sector, used to compose the predicted system name.';
COMMENT ON COLUMN transform.pred_boxel_first.boxel_index IS 'Always 0, the first index the generator assigns.';
COMMENT ON COLUMN transform.pred_boxel_first.x IS 'Centre x of the sector cube, ly. NEVER the system''s position: it may be anywhere in the 1280 ly cube, or not exist.';
COMMENT ON COLUMN transform.pred_boxel_first.y IS 'Centre y of the sector cube, ly. See x.';
COMMENT ON COLUMN transform.pred_boxel_first.z IS 'Centre z of the sector cube, ly. See x.';

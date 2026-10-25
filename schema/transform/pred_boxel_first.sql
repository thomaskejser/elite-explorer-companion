CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.pred_boxel_first;

CREATE TABLE transform.pred_boxel_first (
    sector_id   BIGINT  NOT NULL,
    cube_id     VARCHAR NOT NULL,
    mass_code   VARCHAR NOT NULL,
    sub_cube_id INTEGER NOT NULL,
    sector      VARCHAR NOT NULL,
    boxel_index BIGINT  NOT NULL,
    x           DOUBLE  NOT NULL,
    y           DOUBLE  NOT NULL,
    z           DOUBLE  NOT NULL,
    gated_by    VARCHAR,
    p_exist     DOUBLE  NOT NULL CHECK (p_exist > 0 AND p_exist <= 1),
    PRIMARY KEY (sector_id, mass_code, cube_id)
);

INSERT INTO transform.pred_boxel_first
WITH occupied AS (
  SELECT sector_id, mass_code, cube_id, min(boxel_index) AS lowest
  FROM main.system_known
  WHERE mass_code IN ('g', 'h') AND sub_cube_id = 0 AND sector_id > 0
  GROUP BY 1, 2, 3
),
first_known AS (
  SELECT sector_id, mass_code, cube_id FROM occupied WHERE lowest = 0
),
known AS (
  SELECT sector_id, count(*) AS n FROM main.system_known WHERE sector_id > 0 GROUP BY 1
),
grid AS (
  SELECT s.sector_id, s.sector,
         s.sector_id % 128 AS cx, (s.sector_id // 128) % 128 AS cy, s.sector_id // 16384 AS cz,
         CASE WHEN coalesce(k.n, 0) < 1000 THEN 1 WHEN k.n < 10000 THEN 2
              WHEN k.n < 50000 THEN 3 ELSE 4 END AS band,
         EXISTS (SELECT 1 FROM occupied o WHERE o.sector_id = s.sector_id AND o.mass_code = 'h') AS any_h,
         EXISTS (SELECT 1 FROM first_known f WHERE f.sector_id = s.sector_id AND f.mass_code = 'h') AS has_h0,
         (SELECT count(*) FROM occupied o WHERE o.sector_id = s.sector_id AND o.mass_code = 'g') AS g_boxels,
         (SELECT count(*) FROM first_known f WHERE f.sector_id = s.sector_id AND f.mass_code = 'g') AS g_first
  FROM main.sector s
  LEFT JOIN known k ON k.sector_id = s.sector_id
  WHERE s.sector_id > 0
),
rate AS (
  SELECT cy, band,
         (sum(any_h::INTEGER) + 1) / (count(*) + 2) AS h_held,
         (count(*) FILTER (WHERE has_h0) + 1) / (count(*) FILTER (WHERE any_h) + 2) AS h_from_0,
         (sum(g_boxels) FILTER (WHERE has_h0) + 1) / (8 * count(*) FILTER (WHERE has_h0) + 2) AS g_held,
         (sum(g_first) + 1) / (sum(g_boxels) + 2) AS g_from_0
  FROM grid GROUP BY 1, 2
),
band_rate AS (
  SELECT band,
         (sum(any_h::INTEGER) + 1) / (count(*) + 2) AS h_held,
         (count(*) FILTER (WHERE has_h0) + 1) / (count(*) FILTER (WHERE any_h) + 2) AS h_from_0,
         (sum(g_boxels) FILTER (WHERE has_h0) + 1) / (8 * count(*) FILTER (WHERE has_h0) + 2) AS g_held,
         (sum(g_first) + 1) / (sum(g_boxels) + 2) AS g_from_0
  FROM grid GROUP BY 1
),
boxel AS (
  SELECT 'h' AS mass_code, 0 AS bx, 0 AS bv, 0 AS bz, 1280 AS size
  UNION ALL
  SELECT 'g', a.bx, b.bv, c.bz, 640
  FROM range(2) a(bx), range(2) b(bv), range(2) c(bz)
),
placed AS (
  SELECT g.sector_id, g.sector, b.mass_code, g.cy, g.band,
         b.bx + 128 * b.bv + 16384 * b.bz AS n,
         -49985 + g.cx * 1280 + (b.bx + 0.5) * b.size AS x,
         -40985 + g.cy * 1280 + (b.bv + 0.5) * b.size AS y,
         -24105 + g.cz * 1280 + (b.bz + 0.5) * b.size AS z
  FROM grid g, boxel b
),
named AS (
  SELECT p.*,
         chr(65 + (p.n % 26)::INTEGER) || chr(65 + ((p.n // 26) % 26)::INTEGER)
         || '-' || chr(65 + ((p.n // 676) % 26)::INTEGER) AS cube_id
  FROM placed p
)
SELECT n.sector_id, n.cube_id, n.mass_code, 0, n.sector, 0, n.x, n.y, n.z,
       CASE WHEN n.mass_code = 'g' AND h.sector_id IS NULL THEN n.sector || ' AA-A h0' END,
       round(CASE WHEN n.mass_code = 'h'
                  THEN CASE WHEN o.sector_id IS NOT NULL THEN 1.0 ELSE coalesce(r.h_held, br.h_held) END
                       * coalesce(r.h_from_0, br.h_from_0)
                  ELSE CASE WHEN o.sector_id IS NOT NULL THEN 1.0 ELSE coalesce(r.g_held, br.g_held) END
                       * coalesce(r.g_from_0, br.g_from_0) END, 6)
FROM named n
LEFT JOIN occupied o
  ON o.sector_id = n.sector_id AND o.mass_code = n.mass_code AND o.cube_id = n.cube_id
LEFT JOIN first_known h
  ON h.sector_id = n.sector_id AND h.mass_code = 'h' AND h.cube_id = 'AA-A'
LEFT JOIN rate r ON r.cy = n.cy AND r.band = n.band
LEFT JOIN band_rate br ON br.band = n.band
WHERE o.lowest IS DISTINCT FROM 0;

COMMENT ON TABLE transform.pred_boxel_first IS
'TRANSFORM: the first system, index 0, of every grid sector''s h boxel (<sector> AA-A h0) and of each of its eight g boxels (<sector> AA-A g0 ... DL-Y g0), where main.system_known does not hold it -- the boxel-predicted rows the gap enumeration cannot reach, because a gap needs two known indices to sit between and an empty or one-system boxel has none. Rebuilt on every main.system_predicted load, safe to drop.

A boxel''s letters encode its place in the sector: n = bx + 128 by + 16384 bz over the boxel''s grid steps along x, y and z, written as letters n mod 26, n div 26 mod 26, then n div 676 mod 26. An h boxel is the whole 1280 ly sector, so it is always AA-A; the eight 640 ly g boxels are AA-A, BA-A, YE-A, ZE-A, EG-Y, FG-Y, CL-Y and DL-Y, whose known systems average at exactly those octants.

*** NEVER CERTAIN: A KNOWN HIGHER INDEX DOES NOT PROVE INDEX 0. *** A sector''s known indices in one boxel form an unbroken run, but the run need not start at 0. Just below the galactic plane (sector layer cy = 31) the h numbering continues from the sector above: Byaa Eurk holds AA-A h0-h5 and the sector under it, Gru Drye, h39-h44; in 1,348 of 1,778 such vertical pairs the lower sector''s lowest known index exceeds the upper one''s highest, and the commander found no h0 in nine sectors whose higher indices are known (Flyiedge h39-h55, Nyeajoa h41-h47). So the row is a guess twice over: that the boxel holds any system, and that its numbering starts here. p_exist carries both, so the row''s object probabilities are p(exists) x p(object | exists). The commander marks a probe that does not exist as wrong, which removes it.

*** A g ROW IS GATED ON THE SECTOR''S h0. *** A sector whose h0 is known has more of its g boxels occupied at every level of exploration (74% against 4% of sectors with some known g system under 1,000 known systems; 100% against 97% above 50,000), so a g probe is offered only behind one. gated_by is NULL where the h0 is known; otherwise it names the h0, and the overlay offers the row only once the commander has plotted or visited that system.

Grid sectors only (sector_id > 0): a hand-authored sector has no grid cell, so its boxel letters are not fixed by position.';

COMMENT ON COLUMN transform.pred_boxel_first.sector_id IS 'main.sector.sector_id, the grid cell cx + 128 cy + 16384 cz.';
COMMENT ON COLUMN transform.pred_boxel_first.cube_id IS 'The boxel''s letter triple, from its place in the sector (see the table comment): AA-A for h, one of eight for g.';
COMMENT ON COLUMN transform.pred_boxel_first.mass_code IS 'h or g.';
COMMENT ON COLUMN transform.pred_boxel_first.sub_cube_id IS 'Always 0: a g or h boxel''s place fits in the three letters, so the name carries no number before a hyphen.';
COMMENT ON COLUMN transform.pred_boxel_first.sector IS 'The sector NAME from main.sector, used to compose the predicted system name.';
COMMENT ON COLUMN transform.pred_boxel_first.boxel_index IS 'Always 0, the first index the generator assigns.';
COMMENT ON COLUMN transform.pred_boxel_first.x IS 'Centre x of the boxel, ly. NEVER the system''s position: it may be anywhere in the boxel, or not exist.';
COMMENT ON COLUMN transform.pred_boxel_first.y IS 'Centre y of the boxel, ly. See x.';
COMMENT ON COLUMN transform.pred_boxel_first.z IS 'Centre z of the boxel, ly. See x.';
COMMENT ON COLUMN transform.pred_boxel_first.p_exist IS 'The chance the system exists, 6 dp; main.system_predicted multiplies every object probability by it. p(held) x p(from 0), both measured over grid sectors in the same sector layer (cy, not mirrored about the plane, because the layers either side of it number differently) and the same exploration band (under 1,000, under 10,000, under 50,000, 50,000 or more known systems). p(held) is 1.0 when the boxel already has a known system; otherwise, for h, the share of those sectors with any h system known, and for g, the share of g boxels holding a known system over the sectors whose h0 is known. p(from 0) is the share of held boxels whose index 0 is known: about 0.97 for h in the layer above the plane and about 0.11 in the layer below it. A cell with no data falls back to the exploration band alone. Every rate is smoothed as (found + 1) / (possible + 2), so a cell of a few sectors reads as unlikely rather than impossible or certain. *** NOT CALIBRATED, AND SO FAR TOO HIGH. *** It measures how often comparable sectors have such a system FOUND, which ignores that this sector has been looked at without finding one; and the best-explored sectors cannot supply the true rate, because a sector is explored heavily because it is dense (one layer above the plane, every sector with 10,000-50,000 known systems has an h system found). The commander''s checks are the only ground truth: the first 19 h0 probes checked, with p_exist summing to 5.0, all turned out absent.';
COMMENT ON COLUMN transform.pred_boxel_first.gated_by IS 'For a g row whose sector''s AA-A h0 is not known: that h0''s name, which the overlay must have seen or visited before it offers the row. NULL for every h row and for a g row whose h0 is known.';

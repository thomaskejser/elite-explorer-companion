CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.system_unfound;

CREATE TABLE transform.system_unfound (
    system     VARCHAR NOT NULL PRIMARY KEY,
    type       VARCHAR NOT NULL,
    x          DOUBLE,
    y          DOUBLE,
    z          DOUBLE,
    dist_ly    DOUBLE  NOT NULL CHECK (dist_ly > 0 AND dist_ly <= 1000),
    plx_snr    DOUBLE  NOT NULL CHECK (plx_snr >= 3),
    vmag       DOUBLE,
    sp_type    VARCHAR,
    band       VARCHAR NOT NULL CHECK (band IN ('near', 'mid')),
    sector_id  BIGINT,
    sector     VARCHAR,
    nearest    VARCHAR,
    nearest_ly DOUBLE
);

INSERT INTO transform.system_unfound
    (system, type, x, y, z, dist_ly, plx_snr, vmag, sp_type, band, sector_id, sector,
     nearest, nearest_ly)
WITH cand AS (
    SELECT c.system, c.type, p.plx / p.eplx AS snr,
           3.26156 * 1000 / p.plx AS dist_ly,
           -3.26156 * 1000 / p.plx * cos(radians(p.glat)) * sin(radians(p.glon)) AS x,
            3.26156 * 1000 / p.plx * sin(radians(p.glat))                        AS y,
            3.26156 * 1000 / p.plx * cos(radians(p.glat)) * cos(radians(p.glon)) AS z,
           p.vmag, p.sp_type
    FROM main.system_catalog c
    JOIN staging.catalog_parallax p ON p.system = c.system
    WHERE c.system_id IS NULL
      AND p.usable AND p.plx > 0 AND p.eplx > 0 AND p.glon IS NOT NULL
      AND p.plx / p.eplx >= 3
      AND 3.26156 * 1000 / p.plx < 1000
    QUALIFY row_number() OVER (PARTITION BY c.system ORDER BY p.plx / p.eplx DESC) = 1
),
hand_named AS (
    SELECT system_in_sector AS s, x, y, z FROM main.system_known WHERE sector_id = 0
),
nearest AS (
    SELECT c.system,
           min_by(h.s, sqrt(pow(c.x-h.x,2) + pow(c.y-h.y,2) + pow(c.z-h.z,2))) AS nearest,
           min(sqrt(pow(c.x-h.x,2) + pow(c.y-h.y,2) + pow(c.z-h.z,2)))         AS nearest_ly
    FROM cand c JOIN hand_named h
      ON abs(c.x-h.x) < 20 AND abs(c.y-h.y) < 20 AND abs(c.z-h.z) < 20
    GROUP BY 1
),
sec AS (
    SELECT c.system,
           min_by(s.sector_id, pow(c.x-s.x,2) + pow(c.y-s.y,2) + pow(c.z-s.z,2)) AS sector_id,
           min_by(s.sector,    pow(c.x-s.x,2) + pow(c.y-s.y,2) + pow(c.z-s.z,2)) AS sector
    FROM cand c CROSS JOIN main.sector s
    WHERE s.sector_id <> 0
    GROUP BY 1
)
SELECT c.system, c.type, round(c.x, 4), round(c.y, 4), round(c.z, 4),
       round(c.dist_ly, 2), round(c.snr, 2), c.vmag, c.sp_type,
       CASE WHEN c.dist_ly < 300 AND c.snr >= 10 THEN 'near' ELSE 'mid' END,
       sc.sector_id, sc.sector, n.nearest, round(n.nearest_ly, 3)
FROM cand c
LEFT JOIN nearest n USING (system)
LEFT JOIN sec sc USING (system)
WHERE n.nearest_ly IS NULL
   OR n.nearest_ly >= greatest(3.0, 3.0 * c.dist_ly / c.snr);

COMMENT ON TABLE transform.system_unfound IS
'TRANSFORM: the hunting list as this load computes it, shaped exactly as main.system_unfound merges it. Rebuilt on every load from main.system_catalog, staging.catalog_parallax, main.system_known and main.sector; derived, never edited, safe to drop.

A row clears four tests: its system_catalog name has system_id NULL after the alias walk; staging.catalog_parallax gives a usable parallax with plx/e_plx >= 3 placing it inside 1,000 ly; and no hand-named game system lies within max(3 ly, 3 x dist_ly / plx_snr) of the computed position. A catalogue can publish two parallaxes for one name, so the better signal-to-noise wins.

*** IT IS ALSO THE DELETE LIST. *** A row in main.system_unfound that this table does not produce is deleted by etl/system_unfound/delete.sql: the star resolves by name or alias, or is in a dump, so the claim that it cannot be found is false.';

COMMENT ON COLUMN transform.system_unfound.system IS 'The catalogue name, the natural key the merge matches on.';

COMMENT ON COLUMN transform.system_unfound.type IS 'Source catalogue, from main.system_catalog. HIP, GJ or HR in practice -- the three with a parallax.';

COMMENT ON COLUMN transform.system_unfound.x IS
'Game-frame x from parallax and galactic coordinates (x = -Y_gal, y = Z_gal, z = X_gal), rounded to 4 dp so an unchanged star merges as a no-op. Accurate to roughly dist_ly / plx_snr.';

COMMENT ON COLUMN transform.system_unfound.y IS 'Game-frame y, rounded to 4 dp. See x.';

COMMENT ON COLUMN transform.system_unfound.z IS 'Game-frame z, rounded to 4 dp. See x.';

COMMENT ON COLUMN transform.system_unfound.dist_ly IS 'Distance from Sol implied by the parallax, light years, rounded to 2 dp. CHECKed at most 1,000 ly, since rounding can lift 999.996 to 1000.';

COMMENT ON COLUMN transform.system_unfound.plx_snr IS 'plx / e_plx, rounded to 2 dp. CHECKed at least 3.';

COMMENT ON COLUMN transform.system_unfound.vmag IS 'Visual magnitude, copied from staging.catalog_parallax.';

COMMENT ON COLUMN transform.system_unfound.sp_type IS 'Spectral type, copied from staging.catalog_parallax.';

COMMENT ON COLUMN transform.system_unfound.band IS
'near: inside 300 ly with plx_snr >= 10, position trustworthy to about a light year. mid: everything else inside 1,000 ly, where a positional match cannot be made either way.';

COMMENT ON COLUMN transform.system_unfound.sector_id IS
'The main.sector row whose recorded centre is nearest the computed position, sentinel excluded. An approximation near a sector boundary, and only a hint for a mid row. BIGINT here because a sector_id derived from a hand-authored sector''s name hash does not fit INTEGER.';

COMMENT ON COLUMN transform.system_unfound.sector IS 'Name of that nearest-centre sector.';

COMMENT ON COLUMN transform.system_unfound.nearest IS 'The nearest hand-named game system within a 20 ly box, NULL when there is none.';

COMMENT ON COLUMN transform.system_unfound.nearest_ly IS 'Distance to nearest, light years, rounded to 3 dp.';

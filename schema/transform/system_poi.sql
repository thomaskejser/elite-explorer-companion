CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.system_poi;

CREATE TABLE transform.system_poi (
    system_id BIGINT  NOT NULL,
    poi_id    INTEGER NOT NULL,
    system    VARCHAR NOT NULL CHECK (trim(system) <> ''),
    sector    VARCHAR NOT NULL,
    x         DOUBLE,
    y         DOUBLE,
    z         DOUBLE,
    PRIMARY KEY (system_id, poi_id)
);

INSERT INTO transform.system_poi (system_id, poi_id, system, sector, x, y, z)
SELECT k.system_id, k.id_poi,
       CASE WHEN k.sector_id = 0 THEN k.system_in_sector
            ELSE sc.sector || ' ' || k.system_in_sector END,
       sc.sector, k.x, k.y, k.z
FROM main.system_known k
JOIN main.sector sc ON sc.sector_id = k.sector_id
WHERE k.id_poi IS NOT NULL
UNION
SELECT k.system_id, sb.id_poi,
       CASE WHEN k.sector_id = 0 THEN k.system_in_sector
            ELSE sc.sector || ' ' || k.system_in_sector END,
       sc.sector, k.x, k.y, k.z
FROM main.system_body sb
JOIN main.system_known k ON k.system_id = sb.system_id
JOIN main.sector sc      ON sc.sector_id = k.sector_id
WHERE sb.id_poi IS NOT NULL;

COMMENT ON TABLE transform.system_poi IS
'TRANSFORM: the union of the model''s two POI attributions, shaped exactly as main.system_poi merges it. Rebuilt on every load -- derived, never edited, safe to drop.

*** IT READS main, NOT staging. *** main.system_poi adds no facts; it is a SNAPSHOT that exists only so the overlay does not pay for this query, which reaches 10,023 body-level rows by scanning system_body''s 577.6M. Everything it needs already lives in main, so there is no feed to stage and etl/system_poi has no stage.py.

The UNION is a deduplicating one on purpose: a system whose own id_poi and one of whose bodies name the SAME kind must yield one row, and two bodies naming one kind likewise. The primary key holds that to account.

Run it AFTER both --poi phases. It copies id_poi as it finds it, so a half-linked model produces a half-populated snapshot with no complaint.';

COMMENT ON COLUMN transform.system_poi.system_id IS
'Copied from main.system_known.system_id, never reallocated. Not the game''s id64.';

COMMENT ON COLUMN transform.system_poi.poi_id IS
'The POI kind, from system_known.id_poi or system_body.id_poi. Part of the key: one system can hold several kinds, each its own row.';

COMMENT ON COLUMN transform.system_poi.system IS
'The FULL, PASTEABLE system name, composed HERE and nowhere else. *** THIS IS THE ONE PLACE ETL.md''S BAN ON CONCATENATING SECTOR IS LIFTED *** -- the overlay needs a name a commander can paste into the galaxy map. sector_id = 0 is handled explicitly, because blind concatenation yields "crafted Charick Drift", which the map rejects, and 581 POI systems were hit by exactly that.';

COMMENT ON COLUMN transform.system_poi.sector IS
'The sector NAME, copied from main.sector. ''crafted'' for hand-named systems -- that is a sentinel collecting hand-named systems galaxy-wide, not a place. NOT NULL here: sector_id is NOT NULL and the join is an inner one, so a missing sector row means the model is broken and must fail rather than write a nameless POI.';

COMMENT ON COLUMN transform.system_poi.x IS
'The SYSTEM''S galactic x in ly, copied from main.system_known -- never the body''s, which the model does not hold. NULL where system_known has no position, in which case the row cannot be ranked by distance.';

COMMENT ON COLUMN transform.system_poi.y IS 'System galactic y in ly. See x.';
COMMENT ON COLUMN transform.system_poi.z IS 'System galactic z in ly. See x.';

CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.carrier_position;

CREATE TABLE transform.carrier_position (
    callsign VARCHAR NOT NULL PRIMARY KEY,
    system   VARCHAR NOT NULL CHECK (trim(system) <> ''),
    x        DOUBLE,
    y        DOUBLE,
    z        DOUBLE
);

INSERT INTO transform.carrier_position (callsign, system, x, y, z)
SELECT c.callsign,
       CASE WHEN k.sector_id = 0 THEN k.system_in_sector
            ELSE sc.sector || ' ' || k.system_in_sector END,
       k.x, k.y, k.z
FROM main.carrier c
JOIN main.system_known k ON k.system_id = c.system_id
JOIN main.sector sc      ON sc.sector_id = k.sector_id;

COMMENT ON TABLE transform.carrier_position IS
'TRANSFORM: main.carrier joined to main.system_known and main.sector, shaped exactly as main.carrier_position merges it. Rebuilt on every load -- derived, never edited, safe to drop.

*** IT READS main, NOT staging. *** main.carrier_position adds no facts; it exists so the overlay does not pay for this join, which resolves 2,524 reliable carriers through system_known''s 200.7M rows with nothing to probe on -- 1,440 ms warm, 5,224 cold, on a single-threaded event loop where that is the HUD frozen. Materialised it is 1.8 ms. So there is no feed to stage and etl/carrier_position has no stage.py.

The join is an INNER one: a carrier whose system_id is NULL simply has no row here. That is the honest answer -- we do not know where it is -- and it is why this table is smaller than carrier.

Run it AFTER every carrier load. A carrier that jumped keeps its old position here until it does.';

COMMENT ON COLUMN transform.carrier_position.callsign IS
'The carrier identifier, copied from main.carrier and the natural key of both tables. This table answers "where"; carrier answers "what".';

COMMENT ON COLUMN transform.carrier_position.system IS
'The FULL, PASTEABLE system name, composed HERE. *** THIS IS ONE OF THE TWO PLACES ETL.md''S BAN ON CONCATENATING SECTOR IS LIFTED *** (transform.system_poi is the other), because a pasteable name is the entire point of the table. sector_id = 0 is handled explicitly and is the COMMON case here, not the edge: 2,044 of the 2,524 reliable carriers sit in hand-named systems, so blind concatenation made most nearest-carrier names uncopyable -- "crafted Colonia", which the galaxy map rejects.';

COMMENT ON COLUMN transform.carrier_position.x IS
'Galactic x in ly, copied from main.system_known. *** DELIBERATELY NOT the feed''s own Coord_X *** -- one source for every position in the model means a carrier cannot sit at coordinates its system does not have.';

COMMENT ON COLUMN transform.carrier_position.y IS 'Galactic y in ly, from main.system_known. See x.';
COMMENT ON COLUMN transform.carrier_position.z IS 'Galactic z in ly, from main.system_known. See x.';

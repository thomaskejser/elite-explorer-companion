-- carrier: fleet carriers, and how long each has sat still.
-- Database: elite_mapping_v2.duckdb (the model).
-- Load order tier 2 -- system_id is resolved against system_known.
CREATE TABLE IF NOT EXISTS carrier (
    callsign      VARCHAR NOT NULL PRIMARY KEY,
    carrier_name  VARCHAR,
    last_moved    TIMESTAMP,
    last_seen     TIMESTAMP,
    has_universal_cartographics BOOLEAN,
    is_reliable   BOOLEAN,
    system_id     BIGINT
);

-- --------------------------------------------------------------------------
-- COMMENTS. Kept in this file, beside the DDL they describe, so a schema change
-- and its documentation cannot drift apart.
-- --------------------------------------------------------------------------

COMMENT ON TABLE carrier IS
'Fleet carriers and how long each has stayed put. One row per carrier, 88,663 of them, from EDAstro''s fleetcarriers.csv (EDDN-derived, refreshed about every two days). *** THIS IS A SNAPSHOT OF WHERE CARRIERS WERE, NEVER A PROMISE OF WHERE THEY ARE. *** A carrier can jump at any moment and nothing here would know; last_moved is a staleness signal and must be read as one. *** THE TRAP IN THIS TABLE: "not moved in two years" and "definitely still there" are DIFFERENT CLAIMS, and the difference is enormous. *** 30,886 carriers show last_moved more than two years ago, but 30,288 of those have not been SEEN in over a year either -- their position is simply the last thing anybody reported, which for an abandoned carrier could be wrong by the width of the galaxy. Read last_moved WITH last_seen or the table will mislead you: the defensible pool is old last_moved AND recent last_seen, and "seen" is a real independent sighting -- 72,621 carriers have last_seen LATER than last_moved, and reliable ones average 178 EDDN dockings, so somebody has actually been there since it parked. *** AND THEN SPLIT BY REGION, or the pool misleads again. *** 2,524 carriers qualify but 2,124 of them are in the bubble, where a parked carrier helps nobody, and a naive ">5,000 ly from Sol" test counts COLONIA -- a second population hub 22,000 ly out holding 2,571 carriers -- as deep space. Genuine deep space, Colonia excluded, holds 202 reliable carriers, 179 of them selling exploration data. DSSA is 58 of those 202, so the Deep Space Support Array is the LARGEST deep-space network by far and not a minor slice; [IGAU] adds 10 and [STAR] 7, and the remaining 127 are unaffiliated carriers somebody simply left out there. Chosen over Spansh galaxy_stations.json.gz (4.3 GB) and EDSM stations.json.gz (2.7 GB), which carry every station in the galaxy to deliver the same field in 20 MB. LOADED table: etl/carrier/refresh.py, from staging.edastro_fleet_carrier.';

COMMENT ON COLUMN carrier.callsign IS
'The game''s own carrier identifier ("X9K-T7Q", "01AI") and the NATURAL KEY. Unique and permanent, unlike the name: a commander can rename a carrier whenever they like, and 2,688 carriers begin with the word "THE". Never key on the name.';

COMMENT ON COLUMN carrier.carrier_name IS
'The commander-chosen name ("AEGIS OF ACHENAR", "DSSA Distant Worlds"). NOT unique, freely changeable, and frequently blank. Useful for recognising a fleet -- a "DSSA" prefix means the Deep Space Support Array, which parks carriers publicly for years -- but membership is inferred from the name because no roster file exists; EDAstro publishes only DSSAdisplaced.csv, a single displaced entry.';

COMMENT ON COLUMN carrier.last_moved IS
'When the carrier last CHANGED SYSTEM, per EDDN. The reason this table exists: a carrier that has not jumped in years is effectively a permanent station, and that is what makes it worth routing to. *** Meaningless without last_seen. *** The oldest values cluster at 2020-05-11, around the carrier launch, which is as likely to be a data floor as a real date. NULL where EDDN never observed a move.';

COMMENT ON COLUMN carrier.last_seen IS
'When EDDN last received ANY report about this carrier (EDAstro''s LastUpdated). The corrective to last_moved: recent here means somebody has actually been there lately and it really is where we say. Old here means the row is an archaeological record, whatever last_moved claims. Only 22,219 carriers have been seen in the last 90 days out of 88,663.';

COMMENT ON COLUMN carrier.has_universal_cartographics IS
'TRUE if the carrier runs the `exploration` service -- where an explorer sells cartographic data without flying back to the bubble. This is the single practical reason to route to a carrier mid-expedition, which is why one service is promoted to a column while the rest of EDAstro''s Services string is dropped. 811 of the 2,525 reliably-parked carriers have it.';

COMMENT ON COLUMN carrier.system_id IS
'Where the carrier was last reported. REFERENCES system_known.system_id, checked by common.db.check_references rather than by a constraint -- this database declares no foreign keys. Resolved from EDAstro''s SystemAddress, which is the game''s id64: 88,341 of 88,663 carriers (99.6%) resolve. NULL for the rest -- 34 carry no SystemAddress at all and 288 sit in systems system_known has never heard of, and neither is worth inventing a row for. Where an id64 maps to more than one system_known row -- the 96 known duplicate-name defects -- the lowest system_id is taken so the choice is at least stable.';

COMMENT ON COLUMN carrier.is_reliable IS
'TRUE if this carrier can be trusted to still be where we say: it last MOVED over a year ago and was last SEEN within the last 90 days. Both halves are needed and the pair is the whole point of the column -- "has not moved in years" on its own is satisfied by 30,262 carriers that nobody has laid eyes on since, whose recorded position is simply the last thing anyone reported. *** TIME-DEPENDENT, AND ONLY TRUE AS OF THE LAST BUILD. *** It is computed from now() when transform.carrier is built, so a row that was reliable last month can go stale without the flag changing; re-run the loader rather than trusting an old value. Deliberately says nothing about WHERE the carrier is -- 2,124 of the 2,524 reliable ones sit in the bubble and are of no use to an explorer, and Colonia adds another 151. Filter on region as well: genuine deep space holds 202.';

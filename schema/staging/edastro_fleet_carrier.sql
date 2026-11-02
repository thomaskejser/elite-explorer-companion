CREATE TABLE IF NOT EXISTS staging.edastro_fleet_carrier (
    Callsign        VARCHAR,
    Name            VARCHAR,
    Owner           VARCHAR,
    LastUpdated     TIMESTAMP,
    LastMoved       TIMESTAMP,
    LastSystem      VARCHAR,
    SystemAddress   BIGINT,
    Coord_X         DOUBLE,
    Coord_Y         DOUBLE,
    Coord_Z         DOUBLE,
    SolDistance     DOUBLE,
    EstimatedRegion VARCHAR,
    LocationHistory BIGINT,
    DockingsEDDN    BIGINT,
    Services        VARCHAR
);

COMMENT ON TABLE staging.edastro_fleet_carrier IS
'RAW SOURCE (not a work table -- never drop or rebuild): EDAstro''s fleet-carrier roster, downloaded whole from https://edastro.com/mapcharts/files/fleetcarriers.csv by etl/carrier/stage.py. FULL, ~88k rows in 20 MB, EDDN-derived and refreshed roughly every two days.

*** A SNAPSHOT OF WHERE CARRIERS WERE, NEVER OF WHERE THEY ARE. *** A carrier can jump at any moment and no feed would know until somebody docks and reports it. LastMoved is the staleness signal that makes the table usable at all, and it is meaningless without LastUpdated -- see both columns.

Chosen over Spansh''s galaxy_stations.json.gz (4.3 GB) and EDSM''s stations.json.gz (2.7 GB), which carry every station in the galaxy to deliver the same field.

*** THE CALLSIGN REPEATS. *** The feed is not keyed, and some callsigns appear more than once naming DIFFERENT systems. transform.carrier keeps the newest report and declares the key; never assume one row per carrier here.';

COMMENT ON COLUMN staging.edastro_fleet_carrier.Callsign IS
'The game''s permanent carrier identifier ("X9K-T7Q"). The natural key of main.carrier, but NOT unique in this table -- the feed repeats some. Unlike Name, a commander cannot change it.';

COMMENT ON COLUMN staging.edastro_fleet_carrier.Name IS
'Commander-chosen carrier name. NOT unique, freely renamed, often blank. Fleet membership (DSSA, [IGAU], [STAR]) is inferred from a prefix here because no roster file exists -- an inference about a mutable string, so treat a network count as approximate.';

COMMENT ON COLUMN staging.edastro_fleet_carrier.Owner IS
'Owning commander when EDAstro knows it, which is almost never -- overwhelmingly NULL. Not carried into the model.';

COMMENT ON COLUMN staging.edastro_fleet_carrier.LastUpdated IS
'When EDDN last received ANY report about this carrier. Becomes carrier.last_seen. *** THE CORRECTIVE TO LastMoved: *** recent here means somebody has actually been there lately, so the position is worth something; old here means the row is an archaeological record no matter what LastMoved claims.';

COMMENT ON COLUMN staging.edastro_fleet_carrier.LastMoved IS
'When the carrier last CHANGED SYSTEM, per EDDN. Becomes carrier.last_moved, and it is the reason this feed is used at all -- a carrier parked for years is effectively a permanent station. The oldest values cluster around the 2020-05 carrier launch, which is as likely to be a data floor as a real date. NULL where no move was ever observed.';

COMMENT ON COLUMN staging.edastro_fleet_carrier.LastSystem IS
'System name as EDAstro spells it. *** NOT USED AS A KEY *** -- SystemAddress is. Name matching across feeds fabricates systems, because sector.is_crafted is TRUE for 424 real named sectors.';

COMMENT ON COLUMN staging.edastro_fleet_carrier.SystemAddress IS
'The game''s id64 for the carrier''s last reported system, and THE ONLY column the model joins on. 88,341 of 88,663 resolve against system_known.system_id, which is the id64; 34 rows carry none at all.';

COMMENT ON COLUMN staging.edastro_fleet_carrier.Coord_X IS
'EDAstro''s galactic x for the carrier, in ly. *** THE MODEL DELIBERATELY IGNORES IT. *** carrier_position copies coordinates from system_known instead, so every position in the model comes from one source and a carrier cannot sit at coordinates its own system does not have. Useful only for cross-checking that resolution.';

COMMENT ON COLUMN staging.edastro_fleet_carrier.Coord_Y IS 'EDAstro''s galactic y in ly. See Coord_X: not used.';
COMMENT ON COLUMN staging.edastro_fleet_carrier.Coord_Z IS 'EDAstro''s galactic z in ly. See Coord_X: not used.';

COMMENT ON COLUMN staging.edastro_fleet_carrier.SolDistance IS
'Distance from Sol in ly as EDAstro computes it. A convenience, not a measurement of ours -- and the bubble/Colonia/deep-space split the model cares about needs the full coordinates, not this.';

COMMENT ON COLUMN staging.edastro_fleet_carrier.EstimatedRegion IS
'EDAstro''s region guess, free text ("Inner Orion Spur"). NOT main.region, which is keyed on the game''s region id. ESTIMATED, as the name says.';

COMMENT ON COLUMN staging.edastro_fleet_carrier.LocationHistory IS
'How many distinct locations EDDN has seen this carrier at. A measure of how much this carrier moves about -- high means a wanderer whose recorded position is worth little, and it is NOT the same as LastMoved recency.';

COMMENT ON COLUMN staging.edastro_fleet_carrier.DockingsEDDN IS
'How many dockings EDDN has recorded. EVIDENCE OF SIGHTINGS: reliably-parked carriers average 178, which is what makes their positions believable. A count of reports, so it also measures traffic -- a deep-space carrier nobody visits scores low without being any less parked.';

COMMENT ON COLUMN staging.edastro_fleet_carrier.Services IS
'Semicolon-delimited service list ("commodities;contacts;dock;..."). Only ''exploration'' is carried into the model, as carrier.has_universal_cartographics: selling cartographic data without flying home is the one practical reason to route to a carrier mid-expedition. NULL where no services were reported, which is not the same as a carrier having none.';

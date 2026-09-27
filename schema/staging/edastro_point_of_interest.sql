CREATE TABLE IF NOT EXISTS staging.edastro_point_of_interest (
    id                 BIGINT,
    type               VARCHAR,
    type2              VARCHAR,
    categoryId         BIGINT,
    categoryId2        BIGINT,
    name               VARCHAR,
    region             VARCHAR,
    galMapSearch       VARCHAR,
    galMapUrl          VARCHAR,
    coordinates        DOUBLE[],
    summary            VARCHAR,
    descriptionMardown VARCHAR,
    descriptionHtml    VARCHAR,
    solDistance        DOUBLE,
    id64               BIGINT,
    rating             DOUBLE,
    curation           DOUBLE,
    avgStars           DOUBLE,
    votes              BIGINT,
    poiUrl             VARCHAR,
    mainImage          VARCHAR,
    callsign           VARCHAR,
    rare               BOOLEAN,
    source             VARCHAR,
    latitude           DOUBLE,
    longitude          DOUBLE
);

COMMENT ON TABLE staging.edastro_point_of_interest IS
'RAW SOURCE (not a work table -- never drop or rebuild): the EDAstro Galactic Exploration Catalog, downloaded whole from https://edastro.com/gec/json/combined by etl/poi/stage.py. FULL, and small -- a few thousand rows.

*** A CURATED HUMAN CATALOGUE, NOT A CODEX. *** Every row is somewhere a commander thought worth writing up, so it is a taste-weighted sample of the galaxy and NEVER a census of anything. It carries no hud_category and its category ids are the GEC''s own, unrelated to Canonn''s.

*** JOIN ON id64 AND ONLY ON id64. *** `name` is the POI''s own NICKNAME, not the system it sits in; joining on it inflated the 67 known green-gas-giant systems to 117. The whole reason this table is read at all is `type`, which feeds poi.poi for the gec class.';

COMMENT ON COLUMN staging.edastro_point_of_interest.id IS
'The GEC''s own catalogue number. Internal to EDAstro -- not the game''s id64, not our poi_id, and not stable enough to key anything here on.';

COMMENT ON COLUMN staging.edastro_point_of_interest.type IS
'The GEC''s POI category as free text, e.g. ''Green Gas Giants'', ''Nebulae''. THE COLUMN THIS PROJECT ACTUALLY USES: it becomes poi.poi for the gec class. Uncurated, so it overlaps by case and plural (''nebula'' vs ''Nebulae'') -- resolving that is exactly what input/poi.parquet is hand-edited for.';

COMMENT ON COLUMN staging.edastro_point_of_interest.type2 IS
'Optional SECOND category for a POI that belongs to two. Not read by the model: poi.poi_id is one column and the primary `type` is what it takes.';

COMMENT ON COLUMN staging.edastro_point_of_interest.categoryId IS
'Numeric id behind `type`, in the GEC''s own numbering. Unrelated to poi.poi_id and to Canonn''s categories -- do not treat the two as comparable.';

COMMENT ON COLUMN staging.edastro_point_of_interest.categoryId2 IS 'Numeric id behind type2. See categoryId.';

COMMENT ON COLUMN staging.edastro_point_of_interest.name IS
'*** THE POI''S NICKNAME, NOT A SYSTEM NAME. *** "Sacaqawea Space Port", "The Great Annihilator". Reads like a place and is not one; joining it to any system name is the single documented way to corrupt this feed.';

COMMENT ON COLUMN staging.edastro_point_of_interest.region IS
'EDAstro''s region label, free text. Not main.region, which is keyed on the game''s region id.';

COMMENT ON COLUMN staging.edastro_point_of_interest.galMapSearch IS
'The string to paste into the in-game galaxy map search to reach this POI. Usually a real system name, but supplied for NAVIGATION and not guaranteed to resolve -- do not mine it as a system key.';

COMMENT ON COLUMN staging.edastro_point_of_interest.galMapUrl IS 'Deep link into EDAstro''s web galaxy map. Display only.';

COMMENT ON COLUMN staging.edastro_point_of_interest.coordinates IS
'Galactic position as a 3-element [x, y, z] LIST in light years, not three columns. EDAstro''s figure for the POI, which may be a body or a station rather than the system centre -- system_known is authoritative for a system''s position.';

COMMENT ON COLUMN staging.edastro_point_of_interest.summary IS 'One-line human blurb. Display only.';

COMMENT ON COLUMN staging.edastro_point_of_interest.descriptionMardown IS
'Long description in Markdown. *** THE MISSPELLING IS THE FEED''S OWN *** -- it is spelled ''Mardown'' upstream and is kept verbatim, because a staging column renamed to be tidy stops matching the source.';

COMMENT ON COLUMN staging.edastro_point_of_interest.descriptionHtml IS 'The same description rendered to HTML. Display only.';

COMMENT ON COLUMN staging.edastro_point_of_interest.solDistance IS
'Distance from Sol in ly as EDAstro computes it. A CONVENIENCE, not a measurement of ours -- recompute from coordinates if the number matters.';

COMMENT ON COLUMN staging.edastro_point_of_interest.id64 IS
'The game''s 64-bit system address, and THE ONLY column this feed may be joined on. Nullable, and a NULL row simply cannot be placed in the galaxy.';

COMMENT ON COLUMN staging.edastro_point_of_interest.rating IS
'Community rating. A POPULARITY signal about the write-up, carrying no information about rarity -- never let it influence what the prediction engine values.';

COMMENT ON COLUMN staging.edastro_point_of_interest.curation IS 'Curation score the GEC editors assigned. Editorial, not physical.';

COMMENT ON COLUMN staging.edastro_point_of_interest.avgStars IS 'Mean of the community star ratings. See `rating`: taste, not rarity.';

COMMENT ON COLUMN staging.edastro_point_of_interest.votes IS
'How many commanders rated it. A traffic measure -- a low count means few visitors OR a recent entry, and the two cannot be told apart here.';

COMMENT ON COLUMN staging.edastro_point_of_interest.poiUrl IS 'Canonical GEC page for this POI. Display only.';

COMMENT ON COLUMN staging.edastro_point_of_interest.mainImage IS 'URL of the header screenshot. Display only.';

COMMENT ON COLUMN staging.edastro_point_of_interest.callsign IS
'Fleet carrier callsign when the POI IS a carrier. Mostly NULL. main.carrier is authoritative for carriers -- this is not a carrier feed and must not be read as one.';

COMMENT ON COLUMN staging.edastro_point_of_interest.rare IS
'The GEC''s own "rare" flag: an EDITORIAL judgement by the catalogue''s curators, NOT a measured rate. The model''s rarity comes from counting systems, never from this.';

COMMENT ON COLUMN staging.edastro_point_of_interest.source IS 'Where the GEC imported the entry from. Provenance for EDAstro, not for us.';

COMMENT ON COLUMN staging.edastro_point_of_interest.latitude IS
'Surface latitude in degrees when the POI sits on a body, else NULL. A PLANETARY coordinate -- unrelated to the galactic x/y/z in `coordinates`.';

COMMENT ON COLUMN staging.edastro_point_of_interest.longitude IS 'Surface longitude in degrees. See latitude.';

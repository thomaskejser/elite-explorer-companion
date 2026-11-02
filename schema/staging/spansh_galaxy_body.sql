CREATE TABLE IF NOT EXISTS staging.${table} (
    system_id64        BIGINT,
    body_id            BIGINT,
    body_id64          BIGINT,
    name               VARCHAR,
    type               VARCHAR,
    sub_type           VARCHAR,
    dist_to_arrival_ls DOUBLE,
    is_landable        BOOLEAN,
    gravity            DOUBLE,
    earth_masses       DOUBLE,
    radius             DOUBLE,
    surface_temp_k     DOUBLE,
    surface_pressure   DOUBLE,
    volcanism_type     VARCHAR,
    atmosphere_type    VARCHAR,
    terraforming_state VARCHAR,
    solar_masses       DOUBLE,
    solar_radius       DOUBLE,
    spectral_class     VARCHAR,
    luminosity         VARCHAR,
    absolute_magnitude DOUBLE,
    age                BIGINT,
    main_star          BOOLEAN,
    ring_count         INTEGER,
    ring_types         VARCHAR,
    signal_geology     INTEGER,
    signal_biology     INTEGER,
    genuses            VARCHAR,
    update_time        VARCHAR
);

COMMENT ON TABLE staging.${table} IS
'RAW SOURCE (not a work table -- never drop or rebuild): the body level of the Spansh galaxy dump, extracted in the same streaming pass as the matching _system table by common/spansh.py. The ONLY body source that exists at galaxy scale.

*** WINDOW: ${provenance} ***

*** NOT A CENSUS OF THE GALAXY''S BODIES, in any window. *** Only 38.6% of systems have body data at all, and no source here carries a DSS or mapped flag, so a count from this table is a count of what has been REPORTED. Never fit a rate against it without dividing by the systems that could have contributed.

Barycentres are dropped while parsing: they are orbital placeholders with no physical data, and keeping them would inflate every body count.

Downloaded from ${url}.';

COMMENT ON COLUMN staging.${table}.system_id64 IS 'The parent system''s id64, the join to the matching _system table. NOT the body''s own id.';
COMMENT ON COLUMN staging.${table}.body_id IS 'The body''s index WITHIN its system, from the dump''s bodyId. Unique only per system -- never use it alone as a key.';
COMMENT ON COLUMN staging.${table}.body_id64 IS 'The body''s own 64-bit address. Globally unique where present, but NULL on part of the dump, which is why system_id64 plus body_id is the working key.';
COMMENT ON COLUMN staging.${table}.name IS 'FULL body name, system prefix included ("Blae Hypue EW-W f1-3 7 B Ring"). main.system_body stores the suffix relative to the system instead, so the prefix has to be stripped, not assumed absent.';
COMMENT ON COLUMN staging.${table}.type IS 'Coarse class as Spansh spells it: Star, Planet. Barycentre never appears -- the parser drops it.';
COMMENT ON COLUMN staging.${table}.sub_type IS 'The specific type, matching main.body.body ("F (White) Star", "Water world"). Join on this, NOT on spectral_class, which is a bare letter and does not distinguish a main-sequence star from a giant.';
COMMENT ON COLUMN staging.${table}.dist_to_arrival_ls IS 'Distance from the arrival point in light-seconds. A TRAVEL cost, not an orbital radius.';
COMMENT ON COLUMN staging.${table}.is_landable IS 'Whether the body can be landed on. NULL for stars and for unscanned bodies; NULL is not FALSE.';
COMMENT ON COLUMN staging.${table}.gravity IS 'Surface gravity in g. Planets only.';
COMMENT ON COLUMN staging.${table}.earth_masses IS 'Mass in Earth masses. Planets only -- stars carry solar_masses instead.';
COMMENT ON COLUMN staging.${table}.radius IS 'Body radius in km for planets. Stars use solar_radius; the two are in different units and must not be pooled.';
COMMENT ON COLUMN staging.${table}.surface_temp_k IS 'Surface temperature in kelvin. For a star this is the EFFECTIVE temperature, which is what makes it comparable across the HR diagram.';
COMMENT ON COLUMN staging.${table}.surface_pressure IS 'Surface atmospheric pressure. Planets only, NULL where there is no atmosphere.';
COMMENT ON COLUMN staging.${table}.volcanism_type IS 'Volcanism description, NULL for none. A LABEL from the scan, not a rate.';
COMMENT ON COLUMN staging.${table}.atmosphere_type IS 'Atmosphere description, NULL for none.';
COMMENT ON COLUMN staging.${table}.terraforming_state IS 'Terraforming state as reported. GOTCHA: Earth-likes are NOT flagged as candidates here, so this must not be read as scan value.';
COMMENT ON COLUMN staging.${table}.solar_masses IS 'Mass in solar masses. Stars only.';
COMMENT ON COLUMN staging.${table}.solar_radius IS 'Radius in solar radii. Stars only -- see radius.';
COMMENT ON COLUMN staging.${table}.spectral_class IS 'Bare spectral letter (O, B, A...). NOT sufficient to identify a type: a supergiant and a dwarf share a letter. Use sub_type.';
COMMENT ON COLUMN staging.${table}.luminosity IS 'Luminosity class (V, III, Ia...). Together with spectral_class this is what separates a supergiant from a main-sequence star of the same letter.';
COMMENT ON COLUMN staging.${table}.absolute_magnitude IS 'Absolute magnitude. Smaller is brighter -- the scale is inverted, which is the usual way to misread it.';
COMMENT ON COLUMN staging.${table}.age IS 'Stellar age in millions of years. Stars only.';
COMMENT ON COLUMN staging.${table}.main_star IS 'TRUE for the system''s ARRIVAL star. GOTCHA: in g/h-mass systems the neutron star or black hole is NEVER the arrival star, so this is not a filter for "the system contains one".';
COMMENT ON COLUMN staging.${table}.ring_count IS 'Number of rings, counted while parsing, 0 when there are none. Never NULL.';
COMMENT ON COLUMN staging.${table}.ring_types IS 'Comma-joined SORTED DISTINCT ring types ("Icy,Rocky"). Deduplicated, so it says which types are present and NOT how many rings of each.';
COMMENT ON COLUMN staging.${table}.signal_geology IS 'Count of geological surface signals, NULL when the body carries no signal block. Needs a landing to be worth anything.';
COMMENT ON COLUMN staging.${table}.signal_biology IS 'Count of biological surface signals, NULL when the body carries no signal block.';
COMMENT ON COLUMN staging.${table}.genuses IS 'The signal block''s genus list, kept as a JSON string rather than a struct so the parser never has to agree with the dump about its shape.';
COMMENT ON COLUMN staging.${table}.update_time IS 'The dump''s updateTime for the body, as a STRING -- deliberately not cast, because it is the source''s text and a failed cast would silently null it.';

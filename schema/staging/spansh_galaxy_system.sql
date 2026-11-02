CREATE TABLE IF NOT EXISTS staging.${table} (
    system_id64         BIGINT,
    name                VARCHAR,
    x                   DOUBLE,
    y                   DOUBLE,
    z                   DOUBLE,
    population          BIGINT,
    declared_body_count INTEGER,
    scanned_body_count  INTEGER,
    date                TIMESTAMP
);

COMMENT ON TABLE staging.${table} IS
'RAW SOURCE (not a work table -- never drop or rebuild): the system level of the Spansh galaxy dump, streamed out of the gzip by common/spansh.py. One row per system, no bodies -- those are in the matching _body table, extracted in the same pass.

*** WINDOW: ${provenance} *** The table name says the window and that is the only place it is said. Whatever the window, this is the ONLY system source that carries declared_body_count, which is the game''s own assertion at the honk.

Downloaded from ${url}.';

COMMENT ON COLUMN staging.${table}.system_id64 IS
'The GAME''s 64-bit system address, from the dump''s id64. The only reliable join to any other source -- names are not, see ETL.md. Unique within the dump.';

COMMENT ON COLUMN staging.${table}.name IS
'Full system name as Spansh spells it, sector prefix included ("Blae Hypue EW-W f1-3"). NEVER rebuild this by concatenating sector: 424 sectors are genuinely named and the prefix is already here.';

COMMENT ON COLUMN staging.${table}.x IS 'X in ly, Sol-relative, from the dump''s coords struct.';
COMMENT ON COLUMN staging.${table}.y IS 'Y in ly, Sol-relative. Galactic HEIGHT, so a far narrower range than x and z.';
COMMENT ON COLUMN staging.${table}.z IS 'Z in ly, Sol-relative. Large positive z is coreward.';

COMMENT ON COLUMN staging.${table}.population IS
'Inhabited population, 0 for the overwhelming majority. A POPULATION figure, not a traffic or visit count -- it says nothing about whether anyone has explored the system.';

COMMENT ON COLUMN staging.${table}.declared_body_count IS
'What the system DECLARED at the honk: how many bodies exist. NULL when nobody has honked it, and NULL MUST NOT be read as zero. This is the trustworthy body count and it is >= the number of rows the _body table holds for the system -- the gap is data we do not have, not an error.';

COMMENT ON COLUMN staging.${table}.scanned_body_count IS
'How many body objects this dump actually carries for the system -- counted while parsing, NOT reported by the source. Barycentres are excluded, exactly as they are from the _body table, so the two agree. Compare against declared_body_count to see how complete the system is; it is NOT a DSS or mapped flag, and no source here carries one.';

COMMENT ON COLUMN staging.${table}.date IS
'The dump''s own date field for the system, the last time Spansh saw it change. In a DELTA window every row is inside the window by construction, so this cannot be used to widen or narrow the window after the fact.';

CREATE TABLE IF NOT EXISTS staging.system_catalog_alias_curated (
    system_a VARCHAR,
    system_b VARCHAR,
    source   VARCHAR
);

COMMENT ON TABLE staging.system_catalog_alias_curated IS
'RAW SOURCE (not a work table -- never drop or rebuild): input/system_catalog_alias.parquet loaded verbatim by etl/system_catalog_alias/stage.py. The source is a FILE ON DISK rather than a download, and it is HAND-EDITABLE AND AUTHORITATIVE: etl/system_catalog_alias/seed.py writes it once from VizieR, SIMBAD and the NASA Exoplanet Archive and then refuses to overwrite it, so a wrong cross-identification is corrected by editing the file.

Unvalidated here. Ordering, blanks and duplicates are checked by transform.system_catalog_alias, which fails the load rather than let a bad edge through.';

COMMENT ON COLUMN staging.system_catalog_alias_curated.system_a IS
'One endpoint of the asserted identity, a full catalogue or game name in GAME spelling, exactly as the file holds it. Expected to be the lesser of the two strings; not checked until the transform.';

COMMENT ON COLUMN staging.system_catalog_alias_curated.system_b IS
'The other endpoint, exactly as the file holds it. Expected to be the greater string.';

COMMENT ON COLUMN staging.system_catalog_alias_curated.source IS
'Which catalogue asserted the identity, as `<VizieR table tag>:<column>` or `<service>:<method>`. Provenance only, copied verbatim.';

CREATE TABLE IF NOT EXISTS staging.system_catalog_curated (
    system      VARCHAR,
    type        VARCHAR,
    designation VARCHAR
);

COMMENT ON TABLE staging.system_catalog_curated IS
'RAW SOURCE (not a work table -- never drop or rebuild): input/system_catalog.parquet loaded verbatim by etl/system_catalog/stage.py, minus its system_id column. The source is a FILE ON DISK rather than a download, and it is HAND-EDITABLE AND AUTHORITATIVE: etl/system_catalog/seed.py writes it once from VizieR/CDS and the NASA Exoplanet Archive and then refuses to overwrite it.

The parquet''s system_id column is NOT staged. It is always NULL in the file, and main.system_catalog.system_id is resolved by the loader against system_known, never taken from input.

Unvalidated here: blanks and duplicate names are rejected by transform.system_catalog.';

COMMENT ON COLUMN staging.system_catalog_curated.system IS
'The full pasteable catalogue name in GAME spelling ("HIP 1000", "BD+56 1773"), exactly as the file holds it. The natural key once validated.';

COMMENT ON COLUMN staging.system_catalog_curated.type IS
'Which catalogue the row came from (HIP, HD, HR, GJ, LHS, NLTT, LP, SAO, TYC, BD, CD, CPD, KOI), copied verbatim.';

COMMENT ON COLUMN staging.system_catalog_curated.designation IS
'The identifier within its catalogue with the prefix stripped, copied verbatim. VARCHAR because Tycho-2 is three numbers and the Durchmusterungs carry a signed zone.';

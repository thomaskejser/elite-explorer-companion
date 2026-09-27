CREATE TABLE IF NOT EXISTS staging.poi_curated (
    poi_id        INTEGER,
    poi           VARCHAR,
    poi_class     VARCHAR,
    poi_family    VARCHAR,
    needs_landing BOOLEAN,
    sources       VARCHAR
);

COMMENT ON TABLE staging.poi_curated IS
'RAW SOURCE (not a work table -- never drop or rebuild): input/poi.parquet loaded verbatim by etl/poi/stage.py. The source is a FILE ON DISK rather than a download, and it is HAND-EDITED AND AUTHORITATIVE -- it decides which POI kinds the model tracks and what each one is called.

*** THE THREE CATALOGUES DO NOT FEED main.poi. *** canonn_codex_event, edsm_codex_entry and edastro_point_of_interest are staged beside this table so the loader can report kinds they name that this file does not, but nothing merges from them. That is deliberate: deciding whether the GEC''s ''nebula'' and ''Nebulae'' are one POI or two is a judgement no script can make, and a feed that silently added rows would keep re-making it wrongly.

So a new POI kind reaches the model in one way only: somebody edits input/poi.parquet, giving it an UNUSED poi_id. The loader will not allocate one -- see the poi_id column.';

COMMENT ON COLUMN staging.poi_curated.poi_id IS
'The surrogate key, assigned BY HAND in the file. *** REQUIRED, AND NEVER ALLOCATED HERE. *** system_known.id_poi and system_body.id_poi point at it across 200.7M and 577.6M rows, so a key that shifted with row order would silently repoint them; transform.poi rejects a NULL rather than invent one. Reusing a retired id is the same bug wearing a different hat.';

COMMENT ON COLUMN staging.poi_curated.poi IS
'The POI kind, and the NATURAL KEY the merge matches on -- it must equal the source catalogue''s own label exactly (Canonn english_name, EDSM codex name, or EDAstro GEC type), because that string is what common/poi_link.py joins observations on. Rename it here and the observations stop resolving.';

COMMENT ON COLUMN staging.poi_curated.poi_class IS
'Coarse grouping: nsp, anomaly, ggg, guardian, thargoid, gec. Hand-assigned, since only Canonn rows carry a category upstream.';

COMMENT ON COLUMN staging.poi_curated.poi_family IS
'Phenomenon family within a class, NULL where none applies. Hand-assigned here, but the SAME families are recomputed from names by schema/transform/ph_obs.sql -- the two must agree or a phenomenon reclassifies depending on which table you read.';

COMMENT ON COLUMN staging.poi_curated.needs_landing IS
'TRUE when reaching it costs a surface landing rather than a look. Carried per row, not per class, so a router that cannot land filters on it directly.';

COMMENT ON COLUMN staging.poi_curated.sources IS
'''+''-joined set of catalogues that named this kind: canonn, edsm, gec. DOCUMENTATION of where the kind came from, recorded when it was curated -- it is not re-derived from the staged feeds and may lag them.';

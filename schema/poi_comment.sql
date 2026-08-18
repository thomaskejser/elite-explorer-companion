-- poi: the POINT OF INTEREST dimension. One row per distinct kind of thing worth
-- flying to look at. Applied by etl/load_poi.py via common.db.apply_comment_file().

COMMENT ON TABLE poi IS
'REFERENCE DIMENSION: one row per distinct KIND of point of interest we track (260 seeded), the target of system_known.id_poi and system_body.id_poi. A POI is a thing you fly to LOOK at, which the game credits to YOU however many commanders logged it first -- that is exactly what separates this from prediction: a black hole somebody already scanned is worth nothing to you, a Lagrange cloud is worth the same to everyone. So presence of an id_poi must NEVER be read as "already taken". Classes: nsp (Canonn hud_category=''Cloud'', far broader than the name -- crystals, peduncle trees, bulb molluscs and quadripartite pods all announce as "Notable stellar phenomena"), anomaly (the [EKLPQT]nn-Type series), ggg (green gas giants -- a COLOUR BUG not a body type; DEAD_ENDS.md records they cannot be predicted, so the catalogue is the only supply), guardian and thargoid (surface sites), gec (EDAstro Galactic Exploration Catalog). *** Biology (924,883 systems) and Geology (97,788) are DELIBERATELY EXCLUDED *** -- Biology would swamp every other class by an order of magnitude and turn id_poi into a biology flag, and Geology needs a landing rather than a look. LOADED table: input/poi.parquet is authoritative and HAND-CURATED, because deciding whether the GEC''s ''nebula'' and ''Nebulae'' are one POI or two is a judgement no script can make.';

COMMENT ON COLUMN poi.poi_id IS
'Surrogate key, ours not the game''s. Allocated max+1 and NEVER renumbered: system_known.id_poi and system_body.id_poi point here, across 197M and 570M rows, and DuckDB gives no warning if a CREATE OR REPLACE repoints them.';

COMMENT ON COLUMN poi.poi IS
'The POI kind, and the NATURAL KEY the loader matches on -- the source''s own label (Canonn english_name, EDSM codex name, or EDAstro GEC type). Verbatim from the catalogue, so it carries their inconsistencies until hand-curation resolves them.';

COMMENT ON COLUMN poi.poi_class IS
'Coarse grouping: nsp, anomaly, ggg, guardian, thargoid, gec. This is the granularity at which a single id_poi is nearly lossless -- only 8 systems hold more than one CLASS, whereas 32,058 hold more than one FAMILY. Group by this, not by poi, when comparing populations.';

COMMENT ON COLUMN poi.poi_family IS
'Phenomenon family within a class: mollusc, plant, seed_pod, mineral_formation, lagrange_cloud, anomaly. NULL where the classifier recognises nothing. The classifier text is duplicated in etl/build_poi.py, etl/build_system_phenomenon.py and scripts/01_normalize.sql -- CHANGE ALL THREE TOGETHER or phenomena silently reclassify between them.';

COMMENT ON COLUMN poi.needs_landing IS
'TRUE if reaching it costs a surface landing rather than a look -- every guardian and thargoid site. Carried per ROW rather than per class so a router that cannot land can filter on it directly. This is the same criterion that keeps Canonn''s Geology category out of the table entirely.';

COMMENT ON COLUMN poi.sources IS
'''+''-joined set of catalogues that named this kind: canonn, edsm, gec. Canonn is the only one carrying a hud_category and therefore the only reliable classifier; the GEC is a curated POI feed whose `name` column is the POI''s own nickname, never a system name.';

COMMENT ON COLUMN poi.systems IS
'DERIVED, not a dimension attribute: count of system_known rows whose id_poi is this kind. Recomputed by etl/load_poi.py on every run, so a merge can report updates even when input/poi.parquet is untouched. NULL until the --poi phases have populated id_poi. Counts SYSTEM-LEVEL attributions only -- add `bodies` for the total.';

COMMENT ON COLUMN poi.bodies IS
'DERIVED, not a dimension attribute: count of system_body rows whose id_poi is this kind. Recomputed on every run. NULL until the --poi phases have run. A system whose POI is pinned to a named body is counted HERE and not in `systems`, so the two never double-count.';

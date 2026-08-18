-- system_phenomenon: catalogued notable phenomena, one row per (system, class).
-- Applied by etl/build_system_phenomenon.py via common.db.apply_comment_file().

COMMENT ON TABLE system_phenomenon IS
'CATALOGUED notable phenomena, grain (system_id, phenomenon). Every row is an OBSERVATION somebody already reported -- NOTHING HERE IS PREDICTED, which is the exact opposite of system_predicted (that table deletes wrong rows; this one merges and never drops). Two classes: NSP = Notable Stellar Phenomena and anomalies, from Canonn hud_category=''Cloud'' plus EDSM codex anomaly types -- far broader than "cloud" suggests, covering crystals, peduncle trees, bulb molluscs and quadripartite pods, all of which announce as "Notable stellar phenomena" in the nav panel; surface Geology is DELIBERATELY EXCLUDED because it needs a landing, not a look. GGG = green gas giants, the entire known galactic population, a colour bug rather than a body type; DEAD_ENDS.md records that they CANNOT be predicted, so this catalogue is the only supply. Sources are unioned on id64 and NEVER on name: edastro_point_of_interest.name is the POI''s own nickname, so a name join inflates 67 GGG systems to 117. *** DO NOT USE AS AN "EXPLORED" MASK *** -- an NSP counts as YOUR discovery however many commanders got there first, so presence here does NOT devalue a system; system_body is what records exploration.';

COMMENT ON COLUMN system_phenomenon.system_phenomenon_id IS
'Surrogate key, allocated max+1 and NEVER renumbered (ETL.md 3). Ours, not the game''s.';

COMMENT ON COLUMN system_phenomenon.system_id IS
'FK to system_known. Resolved from the codex id64 through staging.sys_bridge; codex rows that resolve to no known system are counted and reported by the builder, never silently dropped. Coordinates and names come from this join on purpose, so they are the EXACT catalogue values rather than whatever a codex report happened to carry.';

COMMENT ON COLUMN system_phenomenon.phenomenon IS
'Class: ''NSP'' (notable stellar phenomena / anomalies) or ''GGG'' (green gas giant). Half of the natural key with system_id. A system can hold both and then has two rows -- never SELECT one class and treat the count as a system total.';

COMMENT ON COLUMN system_phenomenon.kinds IS
'''+''-joined DISTINCT set of phenomenon families seen in this system: mollusc, plant, seed_pod, mineral_formation, lagrange_cloud, anomaly. For GGG it is the Sudarsky class where a source gives one; the generic ''Green Gas Giant'' is kept ONLY when no source gives anything better, because pasting it beside ''Green Class III Gas Giant'' tells you nothing. NULL means every observation fell outside the classifier -- an NSP by hud_category with no recognised family.';

COMMENT ON COLUMN system_phenomenon.observations IS
'Number of codex reports collapsed into this row, across all sources. A POPULARITY measure, not a quantity of phenomena: a heavily-trafficked system gets many reports of one cloud. Do not read it as "how much is there".';

COMMENT ON COLUMN system_phenomenon.first_reported IS
'Earliest report timestamp across sources, NULL where no source dated it (the EDAstro GEC feed carries no date). Discovery date of the phenomenon as far as the catalogues know -- not a guarantee nobody saw it sooner.';

COMMENT ON COLUMN system_phenomenon.last_reported IS
'Latest report timestamp across sources, NULL where no source dated it. Useful as a staleness signal; it is bounded by the dump date, so it can never be more recent than the ingest.';

COMMENT ON COLUMN system_phenomenon.from_canonn IS
'TRUE if canonn_codex_event supplied at least one observation. Kept so a single catalogue can be re-audited or distrusted without rebuilding: Canonn is the only source with a hud_category and therefore the only reliable NSP flag.';

COMMENT ON COLUMN system_phenomenon.from_edsm IS
'TRUE if edsm_codex_entry supplied at least one observation. EDSM has no hud_category, so its rows qualify only through entry-name matching (lagrange / [eklpqt]-type / anomaly) and its GGG rows only ever say ''Green Gas Giant''.';

COMMENT ON COLUMN system_phenomenon.from_gec IS
'TRUE if edastro_point_of_interest (the EDAstro Galactic Exploration Catalog) supplied it. GGG ONLY -- the GEC is a curated POI feed, not a codex, and it is joined on id64 alone because its `name` column is the POI''s nickname.';

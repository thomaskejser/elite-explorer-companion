CREATE TABLE IF NOT EXISTS staging.edsm_codex_entry (
    systemId    BIGINT,
    systemId64  BIGINT,
    systemName  VARCHAR,
    region      VARCHAR,
    type        VARCHAR,
    name        VARCHAR,
    reportedOn  TIMESTAMP
);

COMMENT ON TABLE staging.edsm_codex_entry IS
'RAW SOURCE (not a work table -- never drop or rebuild): EDSM''s complete codex dump, downloaded whole from https://www.edsm.net/dump/codex.json.gz by etl/poi/stage.py. FULL only -- EDSM publishes no incremental codex slice, so this is the whole catalogue every time.

*** ONE ROW PER OBSERVATION, NOT PER SYSTEM AND NOT PER POI KIND. *** A heavily-visited system reports the same phenomenon many times, so counting rows measures commander traffic rather than the galaxy. Reduce to distinct systems before quoting any population.

*** NO hud_category. *** Canonn is the only feed that classifies an entry, so EDSM rows qualify as a POI only through name matching (lagrange / [eklpqt]-type / anomaly) and its green-gas-giant rows only ever spell it ''Green Gas Giant''. Joined to the model on systemId64 and never on name.';

COMMENT ON COLUMN staging.edsm_codex_entry.systemId IS
'EDSM''s OWN internal system number. *** NOT the game''s id64 and not our system_id *** -- it is meaningless outside EDSM and nothing in the model joins on it. Use systemId64.';

COMMENT ON COLUMN staging.edsm_codex_entry.systemId64 IS
'The game''s 64-bit system address, and THE ONLY SAFE JOIN to system_known.system_id, which is the id64. Nullable: rows predating EDSM recording it carry none and cannot be resolved to a system at all.';

COMMENT ON COLUMN staging.edsm_codex_entry.systemName IS
'System name as EDSM spells it. A DISPLAY string, not a key -- never join on it, because sector.is_crafted is TRUE for 424 real named sectors and name matching across feeds fabricates systems that do not exist.';

COMMENT ON COLUMN staging.edsm_codex_entry.region IS
'EDSM''s region label for the system, free text such as ''Galactic Centre''. Not the model''s region: main.region is keyed on the GAME''s region id, which this feed does not carry. Informational only.';

COMMENT ON COLUMN staging.edsm_codex_entry.type IS
'The codex entry''s internal token, e.g. ''codex_ent_l_phn_part_clus_008''. Stable across localisations, which `name` is not, but it carries no category -- the leading segments are not a taxonomy this project can rely on.';

COMMENT ON COLUMN staging.edsm_codex_entry.name IS
'English display name of the entry, e.g. ''L04-Type Anomaly'', ''Green Gas Giant''. THE KEY THIS PROJECT MATCHES ON: it is what poi.poi holds, so a rename upstream silently drops the rows rather than mismatching them.';

COMMENT ON COLUMN staging.edsm_codex_entry.reportedOn IS
'When the observation was filed with EDSM -- the REPORT time, not the discovery time, and certainly not when the phenomenon appeared. Useless as a rate denominator: it measures when people uploaded, and EDSM''s intake rate has changed repeatedly.';

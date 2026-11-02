CREATE TABLE IF NOT EXISTS staging.canonn_codex_event (
    index_id               BIGINT,
    hud_category           VARCHAR,
    english_name           VARCHAR,
    created_at             TIMESTAMP,
    reported_at            TIMESTAMP,
    cmdrName               VARCHAR,
    system                 VARCHAR,
    x                      VARCHAR,
    y                      VARCHAR,
    z                      VARCHAR,
    body                   VARCHAR,
    latitude               VARCHAR,
    longitude              VARCHAR,
    entryid                BIGINT,
    name                   VARCHAR,
    name_localised         VARCHAR,
    category               VARCHAR,
    category_localised     VARCHAR,
    sub_category           VARCHAR,
    sub_category_localised VARCHAR,
    region_name            VARCHAR,
    region_name_localised  VARCHAR,
    id64                   BIGINT
);

COMMENT ON TABLE staging.canonn_codex_event IS
'RAW SOURCE (not a work table -- never drop or rebuild): the Canonn codex, downloaded whole from https://storage.googleapis.com/canonn-downloads/codex.json.gz by etl/region/stage.py. FULL catalogue -- Canonn publishes no delta feed, so this is never a window and a census taken from it is legitimate.

Several tables are built from this one download, which is why the fetch behind it is idempotent: it reuses raw/canonn_codex_event.json.gz rather than pulling 277 MB again.

hud_category = ''Cloud'' is the reliable Notable Stellar Phenomena flag and is broader than it sounds; ''Geology'' needs a landing to confirm.

*** UPLOADED BY PLAYERS IN EVERY LANGUAGE. *** Every _localised column carries whatever language the reporting client ran in, so picking one arbitrarily returns ''Bras Ecu-Croix externe'' rather than ''Outer Scutum-Centaurus Arm''. Take the modal value per key, which is what schema/transform/region.sql does.';

COMMENT ON COLUMN staging.canonn_codex_event.region_name IS
'The region token as the game emits it, e.g. ''$Codex_RegionName_18;''. The number in it is the GAME''s region id and is the only reliable part -- parse it out rather than matching the string.';

COMMENT ON COLUMN staging.canonn_codex_event.region_name_localised IS
'Region display name in the REPORTING CLIENT''s language, so one region_id carries many spellings. English is the plurality, which is what makes a modal pick return it.';

COMMENT ON COLUMN staging.canonn_codex_event.index_id IS
'*** NOT A ROW ID, DESPITE THE NAME. *** Present on 219,012 of 4.7M rows and taking only 51 distinct values, so it identifies nothing and cannot be used as a key. Use entryid for what was found and id64 for where.';

COMMENT ON COLUMN staging.canonn_codex_event.hud_category IS
'The in-game HUD grouping: Geology, Cloud, Biology and four others. Always present. hud_category = ''Cloud'' is the reliable Notable Stellar Phenomena flag and is broader than the word suggests; ''Geology'' needs a landing to confirm.';

COMMENT ON COLUMN staging.canonn_codex_event.english_name IS
'What was found, in English, always present -- e.g. ''Sulphur Dioxide Fumarole''. 1,057 distinct values, matching entryid one for one. Prefer this over name_localised, which is only populated on about 38% of rows and is in the reporter''s language when it is.';

COMMENT ON COLUMN staging.canonn_codex_event.created_at IS
'When the codex entry was created. Coarser than reported_at -- many reports share a timestamp -- so it groups a submission batch rather than dating an individual sighting.';

COMMENT ON COLUMN staging.canonn_codex_event.reported_at IS
'When this sighting was reported, near-unique across the feed. This is the column to use for anything time-ordered.';

COMMENT ON COLUMN staging.canonn_codex_event.cmdrName IS
'The reporting commander, 9,506 of them. A crowd-sourced feed, so coverage follows where players go and is NEVER a uniform sample of the galaxy.';

COMMENT ON COLUMN staging.canonn_codex_event.system IS
'System name as the reporting client sent it. Join on id64 instead: the name is free text from a client and id64 is the game''s own key.';

COMMENT ON COLUMN staging.canonn_codex_event.x IS
'System x coordinate. *** VARCHAR, NOT A NUMBER *** -- cast it before any arithmetic or comparison, or a string sort silently orders -1058 above -2.';

COMMENT ON COLUMN staging.canonn_codex_event.y IS
'System y coordinate. VARCHAR, not a number -- cast before use, as for x.';

COMMENT ON COLUMN staging.canonn_codex_event.z IS
'System z coordinate. VARCHAR, not a number -- cast before use, as for x.';

COMMENT ON COLUMN staging.canonn_codex_event.body IS
'Body name, e.g. ''1 Cassiopeiae A 3 a''. NULL on 348,399 rows, which is the SYSTEM-LEVEL case and not missing data: a Notable Stellar Phenomenon sits in space, not on a body. Treat a NULL as "system-level" and never as "unknown body".';

COMMENT ON COLUMN staging.canonn_codex_event.latitude IS
'Surface latitude of the find. VARCHAR, not a number. NULL wherever the find is not on a surface, which is the same case body NULL marks.';

COMMENT ON COLUMN staging.canonn_codex_event.longitude IS
'Surface longitude of the find. VARCHAR, not a number, NULL for anything not on a surface.';

COMMENT ON COLUMN staging.canonn_codex_event.entryid IS
'The game''s codex entry id -- WHAT was found, 1,057 distinct, always present. This is the stable key for the kind of object; english_name is its label.';

COMMENT ON COLUMN staging.canonn_codex_event.name IS
'The raw codex token, e.g. ''$Codex_Ent_Fumarole_SulphurDioxideMagma_''. Always present. Match on entryid rather than parsing this.';

COMMENT ON COLUMN staging.canonn_codex_event.name_localised IS
'Display name in the REPORTING CLIENT''s language. Populated on only about 38% of rows, so a join or filter on it silently drops the majority of the feed -- use english_name.';

COMMENT ON COLUMN staging.canonn_codex_event.category IS
'Raw top-level codex category token, 3 distinct, always present.';

COMMENT ON COLUMN staging.canonn_codex_event.category_localised IS
'Top-level category in the reporter''s language. About 38% populated and 18 distinct for 3 real categories, the surplus being translations.';

COMMENT ON COLUMN staging.canonn_codex_event.sub_category IS
'Raw sub-category token, 5 distinct, always present.';

COMMENT ON COLUMN staging.canonn_codex_event.sub_category_localised IS
'Sub-category in the reporter''s language. About 38% populated and 31 distinct for 5 real sub-categories.';

COMMENT ON COLUMN staging.canonn_codex_event.id64 IS
'The game''s own system key, always present. *** THE ONLY SAFE JOIN KEY IN THIS TABLE. *** Names arrive as free text from clients; this does not.';

CREATE TABLE IF NOT EXISTS staging.commander_alias (
    system       VARCHAR,
    canonical    VARCHAR,
    system_id    BIGINT,
    asserted_utc TIMESTAMPTZ
);

COMMENT ON TABLE staging.commander_alias IS
'RAW SOURCE (not a work table -- never drop or rebuild): input/commander_alias.parquet loaded verbatim by etl/system_catalog/stage.py. One row per real catalogue star (HIP 105046) this commander has stated is in the game under another name, by pressing the overlay''s alias key on an unfound catalogue star with a route plotted to it. The parquet is HAND-EDITABLE AND AUTHORITATIVE, written and extended by scripts/export_commander_aliases.py from the app-state database''s system_alias, never shrunk by it.

It is an observation in the game, not astronomy: it says which game system the commander flew to, not that two catalogues name the same star. It feeds only main.system_catalog.system_id, through etl/system_catalog/commander.sql, and only for a catalogue name nothing else resolved.';

COMMENT ON COLUMN staging.commander_alias.system IS 'The catalogue name as main.system_catalog spells it.';
COMMENT ON COLUMN staging.commander_alias.canonical IS 'The game system''s name, the last hop of the route that was plotted when the alias was stated.';
COMMENT ON COLUMN staging.commander_alias.system_id IS 'The game''s id64 of that system, from NavRoute.json''s SystemAddress; joins main.system_known.system_id. NULL when the route gave none, and then the row resolves nothing.';
COMMENT ON COLUMN staging.commander_alias.asserted_utc IS 'When the alias was stated in the overlay; a later statement for the same catalogue name replaces an earlier one in the parquet.';

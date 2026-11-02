CREATE TABLE IF NOT EXISTS setting (
    name        VARCHAR      NOT NULL PRIMARY KEY,
    value       VARCHAR      NOT NULL,
    set_utc     TIMESTAMPTZ  NOT NULL
);

COMMENT ON TABLE setting IS
'APP STATE: the overlay''s settings, one row per setting the commander changed from its default; a setting with no row takes the default compiled into the overlay. Written by the overlay''s Settings tab and key rebinding, and carried to a new seed by the install migration.';

COMMENT ON COLUMN setting.name IS
'The setting: key.<action> for a key binding (overlay/src/win/hotkeys.rs setting_key), fss.keep_captures for keeping every FSS capture.';

COMMENT ON COLUMN setting.value IS
'The value as text: a key chord such as shift+ctrl+tab for a binding, true or false for a switch.';

COMMENT ON COLUMN setting.set_utc IS
'When the overlay last wrote this row, in UTC.';

CREATE TABLE IF NOT EXISTS codex_sighting (
    codex          VARCHAR     NOT NULL,
    region_id      BIGINT      NOT NULL,
    sector_id      BIGINT      NOT NULL,
    entry          VARCHAR     NOT NULL,
    category       VARCHAR     NOT NULL,
    systems        INTEGER     NOT NULL,
    system_id      BIGINT      NOT NULL,
    system         VARCHAR     NOT NULL,
    x              DOUBLE,
    y              DOUBLE,
    z              DOUBLE,
    first_reported TIMESTAMPTZ,
    last_reported  TIMESTAMPTZ
);

COMMENT ON TABLE codex_sighting IS
'Where each CODEX ENTRY has been reported, grain (codex, region_id, sector_id): one row per entry, galactic region and sector in which EDSM holds at least one report of it, carrying how many systems there reported it and one of them to fly to. Built by etl/codex_sighting/refresh.py from staging.edsm_codex_entry, the only feed that covers stars and planets as well as biology, geology and phenomena; mirrored into the app-state file for the overlay''s Codex tab, which sets it against the commander''s own CodexEntry journal events.

*** A FLOOR, NOT THE GAME''S LIST. *** An entry absent from a region here may still exist there: nobody has reported it to EDSM. The game publishes no complete list of what each region holds.

*** NOT A POPULATION. *** systems counts commanders'' reports reduced to distinct systems, so it measures where people have flown and uploaded as much as where the thing is.

Merged on the natural key and never deleted: a sighting EDSM stops publishing stays, because it was reported once.';

COMMENT ON COLUMN codex_sighting.codex IS
'The codex entry''s token as EDSM spells it, lower case without the $ and _name; wrapping: ''codex_ent_dab_type''. The journal''s CodexEntry.Name reduces to the same string, which is how the overlay matches the commander''s log against it. Half the natural key with region_id and sector_id.';

COMMENT ON COLUMN codex_sighting.region_id IS
'The galactic region the reports were filed under, resolved from EDSM''s region name to region.region_id. The game files an entry under the region at the 0/0/0 corner of the system''s boxel, which is what EDSM records, so this is the region that counts for the in-game codex and can differ from system_known.region_id near a border.';

COMMENT ON COLUMN codex_sighting.sector_id IS
'The sector of the reporting systems, from system_known. The grain is per sector so that one representative system per sector lets the overlay find a near one without the mirror carrying every report. Reports whose id64 is not in system_known have no sector and are left out; the loader prints how many.';

COMMENT ON COLUMN codex_sighting.entry IS
'English display name. EDSM''s name, except where EDSM gives several entries one generic name (''Non Terraformable'', ''Terraformable'', ''Standard Gas Giant'', ''Green Gas Giant''): those are read off the token, ''_ter_'' as an atmosphere, ''_no_atmos'' as none, so each entry has a name of its own.';

COMMENT ON COLUMN codex_sighting.category IS
'Stars, Planets, Biology, Geology, Phenomena, Thargoid or Guardian. Canonn''s hud_category where Canonn reports the entry (Cloud and Anomaly become Phenomena, Tourist becomes Planets); otherwise Thargoid for EDSM names starting so, Planets for the standard_, trf_, green_ and earth_likes tokens, and Stars for the rest. For grouping on screen, nothing more.';

COMMENT ON COLUMN codex_sighting.systems IS
'Distinct systems in this region and sector with at least one EDSM report of the entry. Summed over a region''s sectors it is the region total, since a system lies in one sector.';

COMMENT ON COLUMN codex_sighting.system_id IS
'The id64 of the first system in this region and sector to report the entry (ties on report time broken by the lower id64), joined to system_known.system_id.';

COMMENT ON COLUMN codex_sighting.system IS
'That system''s name as EDSM spells it, for display and the clipboard. Never a key.';

COMMENT ON COLUMN codex_sighting.x IS
'That system''s coordinates, copied from system_known so the overlay can measure distance without the model.';

COMMENT ON COLUMN codex_sighting.y IS
'See x.';

COMMENT ON COLUMN codex_sighting.z IS
'See x.';

COMMENT ON COLUMN codex_sighting.first_reported IS
'Earliest EDSM report of the entry in this region and sector: when it was uploaded, not when it was found.';

COMMENT ON COLUMN codex_sighting.last_reported IS
'Latest EDSM report of the entry in this region and sector, bounded by the dump date.';

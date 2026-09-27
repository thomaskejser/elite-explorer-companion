CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.carrier;

CREATE TABLE transform.carrier (
    callsign      VARCHAR NOT NULL PRIMARY KEY CHECK (trim(callsign) <> ''),
    carrier_name  VARCHAR,
    last_moved    TIMESTAMP,
    last_seen     TIMESTAMP,
    has_universal_cartographics BOOLEAN NOT NULL,
    is_reliable   BOOLEAN NOT NULL,
    system_id     BIGINT
);

INSERT INTO transform.carrier (callsign, carrier_name, last_moved, last_seen,
                               has_universal_cartographics, is_reliable, system_id)
WITH deduped AS (
    SELECT *, row_number() OVER (PARTITION BY Callsign
                                 ORDER BY LastUpdated DESC NULLS LAST,
                                          LastMoved DESC NULLS LAST,
                                          SystemAddress) AS rn
    FROM staging.edastro_fleet_carrier
    WHERE Callsign IS NOT NULL AND trim(Callsign) <> ''
)
SELECT f.Callsign,
       nullif(trim(coalesce(f.Name, '')), ''),
       f.LastMoved,
       f.LastUpdated,
       lower(coalesce(f.Services, '')) LIKE '%exploration%',
       coalesce(f.LastMoved   < now() - INTERVAL 365 DAY
            AND f.LastUpdated > now() - INTERVAL 90 DAY, false),
       k.system_id
FROM deduped f
LEFT JOIN main.system_known k ON k.system_id = f.SystemAddress
WHERE f.rn = 1;

COMMENT ON TABLE transform.carrier IS
'TRANSFORM: staging.edastro_fleet_carrier deduplicated, resolved to a system_id and scored for reliability, shaped exactly as main.carrier merges it. Rebuilt on every load -- derived, never edited, safe to drop.

The PRIMARY KEY is the validation that matters: the feed is not keyed and repeats callsigns, so this table is where "one row per carrier" first becomes true. A duplicate surviving the dedupe fails HERE rather than colliding in main.

*** IT READS main.system_known, *** to check that the address EDAstro reports is a system the model knows, so it cannot be built against an empty database. There is no id64 -> system_id map any more: system_known.system_id IS the id64, so SystemAddress joins to it directly.

*** A NO-OP RUN WILL STILL REPORT UPDATES, BY DESIGN. *** is_reliable is computed from now(), so carriers cross the 365-day and 90-day boundaries between runs even when the feed has not changed. That is the one place in this project where a non-zero update count on unchanged input is correct rather than a float or IS DISTINCT FROM bug.';

COMMENT ON COLUMN transform.carrier.callsign IS
'The game''s permanent carrier identifier, and the natural key the merge matches on. Made unique here by keeping the NEWEST row per callsign -- ordered on LastUpdated, then LastMoved, then SystemAddress so the choice is deterministic and a re-run does not report a spurious update.';

COMMENT ON COLUMN transform.carrier.carrier_name IS
'Commander-chosen name, trimmed, with blank normalised to NULL. Mutable and not unique -- never key on it.';

COMMENT ON COLUMN transform.carrier.last_moved IS 'EDAstro LastMoved: when the carrier last changed system. NULL where no move was ever observed.';

COMMENT ON COLUMN transform.carrier.last_seen IS 'EDAstro LastUpdated: when EDDN last received any report about this carrier.';

COMMENT ON COLUMN transform.carrier.has_universal_cartographics IS
'TRUE when the Services string contains ''exploration''. NOT NULL: a carrier reporting no services is recorded as FALSE, because the column answers "can I sell data here" and an unknown is a no.';

COMMENT ON COLUMN transform.carrier.is_reliable IS
'Parked over a year ago AND seen within the last 90 days -- both halves, because "has not moved in years" alone is satisfied by carriers nobody has laid eyes on since. NOT NULL: a NULL last_moved or last_seen coalesces to FALSE, since an unobserved carrier is exactly the case this flag exists to exclude. Recomputed from now() on every build -- see the table comment.';

COMMENT ON COLUMN transform.carrier.system_id IS
'EDAstro''s SystemAddress, kept only where main.system_known has that system. It IS the game''s id64, which is what system_known.system_id now holds, so the join is an equality on the key and needs no map. NULL where the carrier reports no address or sits in a system the model has never heard of -- both are left NULL rather than inventing a system.';

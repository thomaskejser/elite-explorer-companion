CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.system_phenomenon;

CREATE TABLE transform.system_phenomenon (
    system_phenomenon_id BIGINT    NOT NULL,
    system_id            BIGINT    NOT NULL,
    phenomenon           VARCHAR   NOT NULL,
    kinds                VARCHAR,
    observations         INTEGER   NOT NULL CHECK (observations > 0),
    first_reported       TIMESTAMP,
    last_reported        TIMESTAMP,
    from_canonn          BOOLEAN   NOT NULL,
    from_edsm            BOOLEAN   NOT NULL,
    from_gec             BOOLEAN   NOT NULL,
    PRIMARY KEY (system_id, phenomenon)
);

INSERT INTO transform.system_phenomenon
    (system_phenomenon_id, system_id, phenomenon, kinds, observations,
     first_reported, last_reported, from_canonn, from_edsm, from_gec)
WITH collapsed AS (
    SELECT system_id64, phenomenon,
           count(*)::INTEGER                 AS observations,
           min(reported_at)                  AS first_reported,
           max(reported_at)                  AS last_reported,
           bool_or(source = 'canonn')        AS from_canonn,
           bool_or(source = 'edsm')          AS from_edsm,
           bool_or(source = 'gec')           AS from_gec,
           coalesce(string_agg(DISTINCT nullif(kind, 'Green Gas Giant'), '+'
                               ORDER BY nullif(kind, 'Green Gas Giant')),
                    CASE WHEN phenomenon = 'GGG' THEN 'Green Gas Giant' END) AS kinds
    FROM transform.ph_obs
    GROUP BY 1, 2
),
resolved AS (
    SELECT k.system_id, c.*
    FROM collapsed c
    JOIN main.system_known k ON k.system_id = c.system_id64
)
SELECT coalesce(t.system_phenomenon_id,
                (SELECT coalesce(max(system_phenomenon_id), 0) FROM main.system_phenomenon)
                + row_number() OVER (PARTITION BY t.system_phenomenon_id IS NULL
                                     ORDER BY r.system_id, r.phenomenon)),
       r.system_id, r.phenomenon, r.kinds, r.observations,
       r.first_reported, r.last_reported, r.from_canonn, r.from_edsm, r.from_gec
FROM resolved r
LEFT JOIN main.system_phenomenon t
       ON t.system_id = r.system_id AND t.phenomenon = r.phenomenon;

COMMENT ON TABLE transform.system_phenomenon IS
'TRANSFORM: transform.ph_obs collapsed to one row per (system, phenomenon) and resolved to main.system_known, shaped exactly as main.system_phenomenon merges it. Rebuilt on every load -- derived, never edited, safe to drop.

An observation whose id64 has no main.system_known row is DROPPED here: the model cannot name that system yet. Those are counted by the loader, not lost silently.

system_phenomenon_id is carried over from main for a key already there and allocated max+1 for a new one, so an existing id is never renumbered.';

COMMENT ON COLUMN transform.system_phenomenon.system_phenomenon_id IS
'Surrogate id. Copied from main.system_phenomenon when the (system_id, phenomenon) key exists, else allocated above the current maximum. Never reused, never the merge key.';

COMMENT ON COLUMN transform.system_phenomenon.system_id IS
'main.system_known.system_id, which is the game''s id64. Half of the natural key.';

COMMENT ON COLUMN transform.system_phenomenon.phenomenon IS
'NSP or GGG. Half of the natural key.';

COMMENT ON COLUMN transform.system_phenomenon.kinds IS
'The distinct kind labels seen for this key, joined with +. For GGG it is ''Green Gas Giant'' unless Canonn named something more specific. Heuristic labels parsed from names -- see transform.ph_obs.kind.';

COMMENT ON COLUMN transform.system_phenomenon.observations IS
'Reports across all three feeds. Measures how often commanders reported it, NOT how many phenomena the system holds.';

COMMENT ON COLUMN transform.system_phenomenon.first_reported IS
'Earliest timestamped report. NULL when only the GEC names it. Not a discovery date.';

COMMENT ON COLUMN transform.system_phenomenon.last_reported IS
'Latest timestamped report. NULL when only the GEC names it.';

COMMENT ON COLUMN transform.system_phenomenon.from_canonn IS
'TRUE when at least one report came from the Canonn codex.';

COMMENT ON COLUMN transform.system_phenomenon.from_edsm IS
'TRUE when at least one report came from the EDSM codex.';

COMMENT ON COLUMN transform.system_phenomenon.from_gec IS
'TRUE when the EDAstro Galactic Exploration Catalog lists it. GGG only -- the GEC feeds nothing else here.';

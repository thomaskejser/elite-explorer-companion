CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.poi;

CREATE TABLE transform.poi (
    poi_id        INTEGER NOT NULL PRIMARY KEY,
    poi           VARCHAR NOT NULL UNIQUE CHECK (trim(poi) <> ''),
    poi_class     VARCHAR NOT NULL CHECK (poi_class IN
                      ('nsp', 'anomaly', 'ggg', 'guardian', 'thargoid', 'gec')),
    poi_family    VARCHAR,
    needs_landing BOOLEAN NOT NULL,
    sources       VARCHAR,
    systems       INTEGER,
    bodies        INTEGER
);

INSERT INTO transform.poi
    (poi_id, poi, poi_class, poi_family, needs_landing, sources, systems, bodies)
WITH sys AS (
    SELECT id_poi AS poi_id, CAST(count(*) AS INTEGER) AS n
    FROM main.system_known WHERE id_poi IS NOT NULL GROUP BY 1
),
bod AS (
    SELECT id_poi AS poi_id, CAST(count(*) AS INTEGER) AS n
    FROM main.system_body WHERE id_poi IS NOT NULL GROUP BY 1
),
linked AS (SELECT count(*) AS n FROM sys)
SELECT c.poi_id, trim(c.poi), c.poi_class, c.poi_family,
       c.needs_landing, c.sources,
       CASE WHEN (SELECT n FROM linked) = 0 THEN NULL ELSE coalesce(sys.n, 0) END,
       CASE WHEN (SELECT n FROM linked) = 0 THEN NULL ELSE coalesce(bod.n, 0) END
FROM staging.poi_curated c
LEFT JOIN sys ON sys.poi_id = c.poi_id
LEFT JOIN bod ON bod.poi_id = c.poi_id;

COMMENT ON TABLE transform.poi IS
'TRANSFORM: staging.poi_curated plus the two derived counts, shaped exactly as main.poi merges it. Rebuilt on every load -- derived, never edited, safe to drop.

Its constraints ARE the validation of the hand-edited file: a missing poi_id, a duplicate name, a blank name or a class outside the six fails HERE, before anything reaches main. That is the whole reason this table exists rather than merging the parquet directly.

*** IT READS main. *** Unlike the other transforms, systems and bodies are counted from main.system_known and main.system_body, because they describe how many rows point AT each dimension row -- there is nowhere else they could come from. So this table cannot be built against an empty database, and the counts describe the model as it stands at load time, not the source.';

COMMENT ON COLUMN transform.poi.poi_id IS
'Taken from the curated file, NEVER allocated. NOT NULL is enforced here so a hand-edit that forgets an id fails loudly instead of having one invented by row order.';

COMMENT ON COLUMN transform.poi.poi IS
'The natural key the merge matches on, trimmed. UNIQUE is enforced above: two curated rows sharing a name would merge two POI kinds into one, silently.';

COMMENT ON COLUMN transform.poi.poi_class IS
'Restricted to the six classes the model knows. A typo here would otherwise create a seventh class that every group-by then reports as real.';

COMMENT ON COLUMN transform.poi.poi_family IS 'Copied from the curated file. NULL where the curator recognised no family.';

COMMENT ON COLUMN transform.poi.needs_landing IS 'Copied from the curated file.';

COMMENT ON COLUMN transform.poi.sources IS 'Copied from the curated file. Not re-derived from the staged feeds.';

COMMENT ON COLUMN transform.poi.systems IS
'Count of main.system_known rows whose id_poi is this kind. *** NULL, NOT ZERO, WHEN NOTHING IS LINKED YET *** -- before the --poi phases run, every count would be 0, and writing that would assert "this POI occurs nowhere" when the truth is "nobody has looked". A genuine zero after linking IS written as 0.';

COMMENT ON COLUMN transform.poi.bodies IS
'Count of main.system_body rows whose id_poi is this kind, NULL until linking has run. A POI pinned to a named body is counted HERE and not in systems, so the two never double-count.';

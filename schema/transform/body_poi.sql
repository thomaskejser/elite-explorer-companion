CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.body_poi;

CREATE TABLE transform.body_poi (
    system_id BIGINT  NOT NULL,
    body      VARCHAR NOT NULL,
    poi_id    INTEGER NOT NULL,
    source    VARCHAR NOT NULL,
    PRIMARY KEY (system_id, body, poi_id)
);

INSERT INTO transform.body_poi (system_id, body, poi_id, source)
WITH canonn AS (
  SELECT sb.system_id, sb.system_body AS body, sb.poi_id
  FROM main.system_body sb
  WHERE sb.poi_id IS NOT NULL
),
gec AS (
  SELECT system_id, poi_id, regexp_extract(after, '^ ((?:[A-Z]{1,4} )?[0-9]+(?: [a-z]\b){0,3})', 1) AS mention
  FROM (
    SELECT g.id64 AS system_id, p.poi_id,
           unnest(list_slice(string_split(coalesce(g.summary, '') || ' ' || coalesce(g.descriptionMardown, ''),
                                          g.galMapSearch), 2, -1)) AS after
    FROM staging.edastro_point_of_interest g
    JOIN main.poi p ON p.poi = g.type
    WHERE g.id64 IS NOT NULL AND g.galMapSearch IS NOT NULL
  )
  WHERE regexp_extract(after, '^ ((?:[A-Z]{1,4} )?[0-9]+(?: [a-z]\b){0,3})', 1) <> ''
),
gec_candidate AS (
  SELECT system_id, poi_id, mention, k AS trimmed,
         array_to_string(list_slice(string_split(mention, ' '), 1, len(string_split(mention, ' ')) - k), ' ') AS body
  FROM gec, range(0, 4) t(k)
  WHERE len(string_split(mention, ' ')) - k >= 1
),
gec_body AS (
  SELECT system_id, poi_id, arg_min(body, trimmed) AS body
  FROM gec_candidate c
  WHERE EXISTS (SELECT 1 FROM main.system_body sb
                WHERE sb.system_id = c.system_id AND sb.system_body = c.body)
  GROUP BY system_id, poi_id, mention
)
SELECT system_id, body, poi_id, 'canonn' FROM canonn
UNION
SELECT g.system_id, g.body, g.poi_id, 'gec'
FROM gec_body g
WHERE NOT EXISTS (SELECT 1 FROM canonn c
                  WHERE c.system_id = g.system_id AND c.body = g.body AND c.poi_id = g.poi_id);

COMMENT ON TABLE transform.body_poi IS
'TRANSFORM: every POI placed on a named body, shaped exactly as main.body_poi merges it. Rebuilt on every load, derived, safe to drop. A GEC mention is the system''s full name followed by a designation; trailing lower-case words are dropped one at a time until the designation is a body system_body holds, so "1 a lovely view" places the POI on body 1 when there is no 1 a.';

COMMENT ON COLUMN transform.body_poi.system_id IS 'The game''s id64. See main.body_poi.system_id.';
COMMENT ON COLUMN transform.body_poi.body IS 'The body''s name relative to its system, as system_body.system_body spells it.';
COMMENT ON COLUMN transform.body_poi.poi_id IS 'REFERENCES poi.poi_id.';
COMMENT ON COLUMN transform.body_poi.source IS '''canonn'' or ''gec''. See main.body_poi.source.';

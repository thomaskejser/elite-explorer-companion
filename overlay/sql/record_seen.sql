CREATE OR REPLACE TEMP TABLE seen_in
  (system VARCHAR, star_class VARCHAR, x DOUBLE, y DOUBLE, z DOUBLE, system_id BIGINT);
INSERT INTO seen_in VALUES (?, ?, ?, ?, ?, ?);
CREATE OR REPLACE TEMP TABLE seen_src AS
SELECT system, max(star_class) AS star_class,
       max(x) AS x, max(y) AS y, max(z) AS z, max(system_id) AS system_id
FROM seen_in WHERE system IS NOT NULL GROUP BY 1;
UPDATE system_seen AS t
SET star_class = coalesce(s.star_class, t.star_class),
    x = coalesce(s.x, t.x), y = coalesce(s.y, t.y),
    z = coalesce(s.z, t.z),
    system_id = coalesce(s.system_id, t.system_id)
FROM seen_src AS s WHERE s.system = t.system;
SELECT s.system FROM seen_src s
WHERE NOT EXISTS (SELECT 1 FROM system_seen t WHERE t.system = s.system);
INSERT INTO system_seen (system, star_class, x, y, z, system_id, sector, first_seen_utc)
SELECT s.system, s.star_class, s.x, s.y, s.z, s.system_id,
       nullif(regexp_extract(s.system, '^(.*) [A-Z][A-Z]-[A-Z] [a-h]\d', 1), ''),
       try_cast(? AS TIMESTAMPTZ)
FROM seen_src s
WHERE NOT EXISTS (SELECT 1 FROM system_seen t WHERE t.system = s.system);
UPDATE system_seen AS t SET is_known = FALSE
FROM {{MODEL}}.system_predicted AS p
WHERE p.system = t.system AND t.is_known IS NULL AND ({{ARRIVAL_T}} IN ({{ALL_CLASSES}}));
SELECT count(*) FROM system_seen t
WHERE t.is_known IS NULL AND ({{ARRIVAL_T}} IN ({{ALL_CLASSES}}));
UPDATE system_seen AS t SET is_known = TRUE
WHERE t.is_known IS NULL AND ({{ARRIVAL_T}} IN ({{ALL_CLASSES}}))
  AND EXISTS (SELECT 1 FROM {{MODEL}}.system_known_probe b WHERE b.system = t.system);

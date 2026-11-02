CREATE OR REPLACE TABLE staging.poi_body_merge AS
SELECT w.system_id, w.body_suffix, coalesce(h.body_no, -1) AS body_no, w.poi_id
FROM staging.poi_body w
LEFT JOIN (SELECT system_id, system_body,
                  coalesce(min(body_no) FILTER (WHERE body_no >= 0), -1) AS body_no
           FROM main.system_body GROUP BY 1, 2) h
       ON h.system_id = w.system_id AND h.system_body = w.body_suffix;

COMMENT ON TABLE staging.poi_body_merge IS
'WORK TABLE, rebuilt by etl/system_body/poi.py and safe to drop: staging.poi_body with the main.system_body key resolved for every (system, body) POI -- the stored body''s lowest real body_no where main.system_body already holds the designation, -1 where the POI report is the first evidence the body exists or its index is unknown.';

COMMENT ON COLUMN staging.poi_body_merge.system_id IS
'The game''s id64 of the system the POI was reported in.';

COMMENT ON COLUMN staging.poi_body_merge.body_suffix IS
'The body''s designation within that system, matched against main.system_body.system_body.';

COMMENT ON COLUMN staging.poi_body_merge.body_no IS
'The body''s index within its system as main.system_body holds it; -1 when unknown.';

COMMENT ON COLUMN staging.poi_body_merge.poi_id IS
'main.poi.poi_id of the rarest POI reported on this body.';

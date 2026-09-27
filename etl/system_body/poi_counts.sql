SELECT
  (SELECT count(*) FROM staging.poi_body_merge s
   WHERE NOT EXISTS (SELECT 1 FROM main.system_body t
                     WHERE t.system_id = s.system_id AND t.system_body = s.body_suffix
                       AND t.body_no = s.body_no)),
  (SELECT count(*) FROM main.system_body t JOIN staging.poi_body_merge s
          ON t.system_id = s.system_id AND t.system_body = s.body_suffix
         AND t.body_no = s.body_no
   WHERE t.id_poi IS DISTINCT FROM s.poi_id),
  (SELECT count(*) FROM main.system_body t
   WHERE t.id_poi IS NOT NULL
     AND NOT EXISTS (SELECT 1 FROM staging.poi_body_merge s
                     WHERE s.system_id = t.system_id AND s.body_suffix = t.system_body
                       AND s.body_no = t.body_no)),
  (SELECT count(DISTINCT s.system_id) FROM staging.poi_body_merge s
   WHERE NOT EXISTS (SELECT 1 FROM main.system_body t WHERE t.system_id = s.system_id));

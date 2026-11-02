SELECT
  (SELECT count(*) FROM main.system_body t JOIN transform.system_body_primary p
          ON t.system_id = p.system_id
   WHERE t.is_primary AND (t.system_body, t.body_no) IS DISTINCT FROM (p.system_body, p.body_no)),
  (SELECT count(*) FROM main.system_body t JOIN transform.system_body_primary p
          ON t.system_id = p.system_id AND t.system_body = p.system_body
         AND t.body_no = p.body_no
   WHERE NOT t.is_primary);

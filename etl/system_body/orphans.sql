SELECT t.system_id, t.system_body, t.body_no, t.source
FROM main.system_body t
WHERE t.source = 'spansh'
  AND NOT EXISTS (SELECT 1 FROM transform.system_body s
                  WHERE s.system_id = t.system_id AND s.system_body = t.system_body
                    AND s.body_no = t.body_no)
LIMIT 20;

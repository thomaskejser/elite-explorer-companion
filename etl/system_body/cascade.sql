UPDATE main.system_body SET is_primary = false
FROM transform.system_body_primary p
WHERE main.system_body.system_id = p.system_id
  AND main.system_body.is_primary
  AND (main.system_body.system_body, main.system_body.body_no)
      IS DISTINCT FROM (p.system_body, p.body_no);

UPDATE main.system_body SET is_primary = true
FROM transform.system_body_primary p
WHERE main.system_body.system_id = p.system_id
  AND main.system_body.system_body = p.system_body
  AND main.system_body.body_no = p.body_no
  AND NOT main.system_body.is_primary;

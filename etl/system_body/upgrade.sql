UPDATE main.system_body SET body_no = u.body_no
FROM (
    SELECT s.system_id, s.system_body, min(s.body_no) AS body_no
    FROM transform.system_body s
    WHERE abs((s.system_id >> 3) % ?) = ? AND s.body_no >= 0
      AND NOT EXISTS (SELECT 1 FROM main.system_body r
                      WHERE r.system_id = s.system_id AND r.system_body = s.system_body
                        AND r.body_no >= 0)
    GROUP BY 1, 2
) u
WHERE main.system_body.system_id = u.system_id
  AND main.system_body.system_body = u.system_body
  AND main.system_body.body_no = -1;

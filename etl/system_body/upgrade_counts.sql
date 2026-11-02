SELECT count(*)
FROM main.system_body t
JOIN (
    SELECT s.system_id, s.system_body
    FROM transform.system_body s
    WHERE abs((s.system_id >> 3) % ?) = ? AND s.body_no >= 0
      AND NOT EXISTS (SELECT 1 FROM main.system_body r
                      WHERE r.system_id = s.system_id AND r.system_body = s.system_body
                        AND r.body_no >= 0)
    GROUP BY 1, 2
) u ON u.system_id = t.system_id AND u.system_body = t.system_body
WHERE t.body_no = -1;

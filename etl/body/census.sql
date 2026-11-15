UPDATE main.body AS t
SET bodies = s.n, observed = s.n > 0
FROM (SELECT b.body_id, coalesce(c.n, 0) AS n
      FROM main.body b
      LEFT JOIN (SELECT lower(type) AS type, sub_type AS body, count(*) AS n
                 FROM staging.spansh_galaxy_body
                 WHERE sub_type IS NOT NULL
                 GROUP BY 1, 2) c ON c.type = b.type AND c.body = b.body) s
WHERE t.body_id = s.body_id
  AND t.bodies IS DISTINCT FROM s.n;

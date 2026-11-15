SELECT
  (SELECT count(*) FROM (SELECT system_id FROM main.system_body
                         WHERE is_primary AND abs((system_id >> 3) % $1) = $2
                         GROUP BY 1 HAVING count(*) > 1)),
  (SELECT count(*) FROM main.system_body sb JOIN main.system_known sk USING (system_id)
   WHERE sb.is_primary AND sk.primary_star_body_id IS NOT NULL
     AND sb.body_id IS DISTINCT FROM sk.primary_star_body_id
     AND abs((sb.system_id >> 3) % $1) = $2 AND abs((sk.system_id >> 3) % $1) = $2);

WITH dual AS (
    SELECT system_id FROM main.system_body WHERE is_primary GROUP BY 1 HAVING count(*) > 1
)
SELECT count(*), coalesce(sum(n - 1), 0)
FROM (SELECT d.system_id, count(*) AS n
      FROM main.system_body b JOIN dual d USING (system_id)
      WHERE b.is_primary GROUP BY 1);

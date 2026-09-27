SELECT t.phenomenon, count(*) AS systems
FROM main.system_phenomenon t
WHERE NOT EXISTS (SELECT 1 FROM transform.system_phenomenon s
                  WHERE s.system_id = t.system_id AND s.phenomenon = t.phenomenon)
GROUP BY 1
ORDER BY 1;

SELECT o.phenomenon,
       count(DISTINCT o.system_id64) AS systems,
       (SELECT count(*) FROM transform.system_phenomenon s
        WHERE s.phenomenon = o.phenomenon) AS resolved
FROM transform.ph_obs o
GROUP BY 1
ORDER BY 1;
